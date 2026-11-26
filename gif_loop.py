# GIF ループツール
# ステップ1：画面なしで、動画の一部分を「行って戻る」往復ループの GIF にする
# ステップ4：おかしな数字を、理由を書いたエラーにする。画面で再生する絵を ffmpeg でまとめて取り出す
# ステップ8：シークバー用に、動画の好きな位置の絵を1枚取り出す
# ステップ9：動画の一部分だけを切り抜いて GIF にできるようにする（スマホの縦向き動画にも対応）
# ステップ10：Discord・X などのファイルサイズの上限に収まるまで、横幅 → fps の順に下げて作り直す
# ステップ12：動画のフレーム数を調べ、時間を「時:分:秒:フレーム」で表したり読み取ったりする
# ステップ15：サイズ上限に「LINE（目安 20MB）」を追加する
# ステップ25：往復させず、順再生を1回だけ再生して止まる GIF も作れるようにする（once=True）
# ステップ32：作っている途中の進み具合を知らせ、途中でやめられるようにする（スマホ版と同じ）
#
# しくみ（ffmpeg の filter：映像に順番に加工をかける機能 を使う）
#   1. 使う範囲だけを読み込む（-ss 開始秒、-t 長さ）
#   2. スピードを変える（setpts：絵を出す時刻を詰めたり延ばしたりする）
#   3. fps（1秒に使う絵の枚数）と横幅をそろえる
#   4. 同じ映像を2つに分け、片方を逆再生（reverse）してうしろにつなぐ（concat）
#      折り返し地点で同じ絵が2回続くとカクッと止まって見えるので、
#      逆再生側の「最初の1枚」と「最後の1枚」は外す
#      例）順再生 0,1,2,3,4 → 逆再生 3,2,1 → また 0 から（重なりなし）
#   5. GIF は 256 色までしか使えないので、この映像に合った色の一覧（パレット）を作ってから保存する
#
# 使い方（確認用）
#   python gif_loop.py 動画 [--start 開始秒] [--end 終了秒] [--width 横幅] [--fps fps] [--speed スピード]
#   例）python gif_loop.py 夕焼け.mp4 --start 2 --end 5

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_START = 0.0    # 使う範囲の開始（秒）
DEFAULT_LENGTH = 3.0   # 終了を指定しないときの長さ（秒）
DEFAULT_WIDTH = 480    # GIF の横幅（ピクセル）。縦は元の比率に合わせて自動
DEFAULT_FPS = 15       # 1秒に使う絵の枚数
DEFAULT_SPEED = 1.0    # 再生スピード（2 で2倍速、0.5 でゆっくり）

# exe にしたアプリから ffmpeg を動かしたとき、黒い画面が一瞬出ないようにする
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class FfmpegMissing(RuntimeError):
    """ffmpeg・ffprobe そのものが見つからないときのエラー"""


class FileProblem(ValueError):
    """ファイルや指定に問題があって、作れないときのエラー（理由は使う人に向けた言葉で書く）"""


class Cancelled(Exception):
    """使う人が［やめる］を押して、作るのをやめたとき（ステップ32）"""


# 進み具合の分け方（ステップ32）。ffmpeg は、まず範囲の絵を全部読み込み（前半）、そのあと GIF に書く（後半）。
# 試したところ、読み込みが全体の 3〜4割、書き込みが残りだったので、前半を 0〜45%、後半を 45〜100% として数える
READ_SHARE = 0.45
SHOWINFO = re.compile(r"Parsed_showinfo_(\d+).*?pts_time:\s*([-\d.]+)")


def run(command):
    """ffmpeg・ffprobe を動かして、結果を返す（日本語のファイル名でも大丈夫なように UTF-8 で受け取る）"""
    try:
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              creationflags=NO_WINDOW)
    except FileNotFoundError:
        raise FfmpegMissing(f"{command[0]} が見つかりません。ffmpeg を入れてから、もう一度試してください")


def probe(path):
    """ffprobe（ファイルの中身を調べる道具）で、動画の長さ・横幅・高さを調べる"""
    if not Path(path).is_file():
        raise FileProblem("ファイルが見つかりません")
    result = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries",
                  "stream=width,height,avg_frame_rate,r_frame_rate:stream_side_data=rotation:format=duration",
                  "-of", "default=noprint_wrappers=1", str(path)])
    if result.returncode != 0:
        raise FileProblem("動画として読めません（壊れているか、動画ではないファイルです）")
    info = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if not info.get("width"):
        raise FileProblem("映像が入っていません")
    try:
        duration = float(info.get("duration", ""))
    except ValueError:
        duration = 0.0
    if duration <= 0:  # 静止画（PNG や JPG）は、映像はあっても長さがない
        raise FileProblem("動画の長さが分かりません（静止画か、壊れた動画かもしれません）")
    width, height = int(info["width"]), int(info["height"])
    # スマホで縦に撮った動画は、横長のまま保存され「90度回して見せる」という印が付いていることがある
    # ffmpeg は回してから加工するので、切り抜きの計算に使う縦横も入れかえておく（ステップ9）
    try:
        rotation = abs(int(float(info.get("rotation", "0")))) % 180
    except ValueError:
        rotation = 0
    if rotation == 90:
        width, height = height, width
    # 1秒あたりのフレーム数（ステップ12：タイム表示用）。「30000/1001」のような分数で届く
    frame_rate = 0.0
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            top, bottom = info.get(key, "0/0").split("/")
            if float(bottom) > 0 and 1 <= float(top) / float(bottom) <= 240:
                frame_rate = float(top) / float(bottom)
                break
        except ValueError:
            continue
    return {"duration": duration, "width": width, "height": height, "frame_rate": frame_rate or DEFAULT_FRAME_RATE}


# ---- タイム（時:分:秒:フレーム）の表示と読み取り（ステップ12） ----

DEFAULT_FRAME_RATE = 30.0  # フレーム数が分からないときに使う
SEEK_MARGIN = 0.001        # 絵を取り出すとき、指定より少しだけ手前から探す（秒）。1フレームの半分よりずっと短い


def seconds_to_timecode(seconds, frame_rate):
    """秒 → 「時:分:秒:フレーム」（例：8.3 秒・30fps → 00:00:08:09）
    フレームは「その1秒の中の何枚目か」（0 から数える）"""
    seconds = max(0.0, seconds)
    whole = int(seconds + 1e-9)
    frame = int((seconds - whole) * frame_rate + 1e-6)  # 計算の小さな誤差で1枚少なくならないよう、ほんの少し足す
    frame = min(frame, round(frame_rate) - 1)
    return f"{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}:{frame:02d}"


def timecode_to_seconds(text, frame_rate):
    """「時:分:秒:フレーム」や秒の数字を、秒にする。読めないときは、理由を書いた ValueError を出す
    受け付ける形：00:00:08:09（時:分:秒:フレーム）、00:08:09（分:秒:フレーム）、08:09（秒:フレーム）、8.3（秒）"""
    text = text.strip()
    if ":" not in text:
        try:
            return float(text)  # 秒の数字
        except ValueError:
            raise ValueError("時:分:秒:フレーム（例：00:00:08:09）か、秒の数字（例：8.3）を入れてください")
    parts = text.split(":")
    if len(parts) > 4 or not all(p.strip().isdigit() for p in parts):
        raise ValueError("時:分:秒:フレーム の形で入れてください（例：00:00:08:09）")
    numbers = [0] * (4 - len(parts)) + [int(p) for p in parts]  # 足りない頭のほうは 0 とみなす
    hours, minutes, secs, frame = numbers
    if minutes >= 60 or secs >= 60:
        raise ValueError("分と秒は 59 までにしてください")
    if frame >= round(frame_rate):
        raise ValueError(f"フレームは 0〜{round(frame_rate) - 1} にしてください（この動画は 1秒 {frame_rate:g} フレーム）")
    return hours * 3600 + minutes * 60 + secs + frame / frame_rate


def snap_to_frame(seconds, frame_rate):
    """いちばん近いフレームの区切りにそろえる"""
    return round(seconds * frame_rate) / frame_rate


def default_output_path(video_path, suffix="loop"):
    """保存先：元の動画と同じ場所に「元の名前_loop.gif」。同じ名前があれば _loop2, _loop3… にして上書きしない
    suffix：名前の後ろに付ける言葉（1回だけの GIF は "once"。ステップ25）"""
    video_path = Path(video_path)
    candidate = video_path.with_name(f"{video_path.stem}_{suffix}.gif")
    number = 2
    while candidate.exists():
        candidate = video_path.with_name(f"{video_path.stem}_{suffix}{number}.gif")
        number += 1
    return candidate


# 入力できる数字の範囲（ステップ4）
WIDTH_RANGE = (16, 1920)    # 横幅（ピクセル）
FPS_RANGE = (1, 50)         # GIF は 1/100 秒単位でしか時間を決められず、50 を超えると多くのソフトで正しく再生されない
SPEED_RANGE = (0.1, 10.0)   # 再生スピード（倍）
HEAVY_FRAMES = 400          # 絵の枚数がこれを超えそうなら「重くなります」と確かめる


def estimate_frames(start, end, fps, speed, once=False):
    """できる GIF のおおよその枚数（順再生＋逆再生。once=True なら順再生だけ）"""
    forward = (end - start) / speed * fps
    return int(forward) if once else int(forward * 2)


def check_settings(start, end, width, fps, speed, duration):
    """おかしな指定がないか調べて、使う人に向けた理由のリストを返す（問題がなければ空のリスト）"""
    problems = []
    if start < 0:
        problems.append("開始は 0 秒以上にしてください")
    if duration > 0 and start >= duration:
        problems.append(f"開始が動画の長さ（{duration:.1f} 秒）を超えています")
    elif end <= start:
        problems.append("終了は、開始より後ろにしてください")
    if not WIDTH_RANGE[0] <= width <= WIDTH_RANGE[1]:
        problems.append(f"横幅は {WIDTH_RANGE[0]}〜{WIDTH_RANGE[1]} にしてください")
    if not FPS_RANGE[0] <= fps <= FPS_RANGE[1]:
        problems.append(f"fps は {FPS_RANGE[0]}〜{FPS_RANGE[1]} にしてください")
    if not SPEED_RANGE[0] <= speed <= SPEED_RANGE[1]:
        problems.append(f"再生スピードは {SPEED_RANGE[0]}〜{SPEED_RANGE[1]:g} 倍にしてください")
    return problems


def check_crop(crop, video_width, video_height):
    """切り抜く範囲（左上の x, y と 横幅, 高さ。元の動画のピクセルで数える）が、動画の中に収まっているか調べる"""
    x, y, w, h = crop
    if w < 16 or h < 16:
        return ["切り抜く範囲が小さすぎます（16 ピクセル以上にしてください）"]
    if x < 0 or y < 0 or x + w > video_width or y + h > video_height:
        return ["切り抜く範囲が、動画の外にはみ出しています"]
    return []


def build_filter(width, fps, speed, crop=None, once=False, watch=False):
    """ffmpeg に渡す加工の手順（filter_complex）を組み立てる
    once=True：逆再生をつながず、順再生だけにする（ステップ25：1回だけ再生して止まる GIF）
    watch=True：読み込んだ絵と書いた絵の1枚ごとに、ffmpeg に知らせを出させる（showinfo。ステップ32：進み具合用）"""
    cropping = f"crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]}," if crop else ""  # 先に切り抜いてから縮める
    head = "showinfo," if watch else ""   # 読み込んだ絵（0番目の showinfo）
    tail = ",showinfo" if watch else ""   # GIF に書く絵（1番目の showinfo）
    if once:
        return (
            f"[0:v]{head}{cropping}setpts=PTS/{speed},fps={fps},scale={width}:-2:flags=lanczos,split[a][b];"
            "[a]palettegen=stats_mode=diff[pal];"
            f"[b][pal]paletteuse=dither=sierra2_4a{tail}"
        )
    return (
        f"[0:v]{head}{cropping}setpts=PTS/{speed},fps={fps},scale={width}:-2:flags=lanczos,split[fwd][tmp];"
        # 逆再生側：最初の1枚を外す → 逆にする → (逆にしたあとの)最初の1枚を外す
        # ＝ 元の「最後の1枚」と「最初の1枚」を外した逆再生になる
        "[tmp]trim=start_frame=1,reverse,trim=start_frame=1,setpts=PTS-STARTPTS[rev];"
        "[fwd][rev]concat=n=2:v=1:a=0,"
        # つないだあとの時刻を、きれいに等間隔にふり直す
        f"setpts=N/({fps}*TB),split[a][b];"
        "[a]palettegen=stats_mode=diff[pal];"   # この映像に合った 256 色を選ぶ
        f"[b][pal]paletteuse=dither=sierra2_4a{tail}"  # 選んだ色で絵を作る（dither：色の境目をなじませる）
    )


def run_watching(command, length, total_frames, report, cancel):
    """ffmpeg を動かしながら、showinfo の知らせを読んで進み具合（0〜1）を report に知らせる（ステップ32）
    前半：読み込んだ絵の時刻 ÷ 範囲の長さ、後半：書いた絵の枚数 ÷ できる枚数
    cancel（threading.Event）が立ったら ffmpeg を止めて Cancelled を出す
    返すもの：(終わったときの番号, 最後の数行の知らせ)"""
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                   creationflags=NO_WINDOW)
    except FileNotFoundError:
        raise FfmpegMissing("ffmpeg が見つかりません。ffmpeg を入れてから、もう一度試してください")
    last_lines, written = [], 0
    try:
        for line in process.stderr:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            match = SHOWINFO.search(line)
            if not match:
                last_lines = (last_lines + [line.rstrip()])[-3:]
                continue
            if match.group(1) == "0":  # 読み込んだ絵
                part = min(1.0, max(0.0, float(match.group(2))) / length) if length > 0 else 1.0
                fraction = READ_SHARE * part
            else:                      # GIF に書いた絵
                written += 1
                fraction = READ_SHARE + (1 - READ_SHARE) * min(1.0, written / max(1, total_frames))
            if report:
                report(fraction)
        process.wait()
        if cancel is not None and cancel.is_set():
            raise Cancelled()
    except Cancelled:
        process.kill()
        process.wait()
        raise
    return process.returncode, "\n".join(last_lines)


def make_pingpong_gif(video_path, output_path=None, start=DEFAULT_START, end=None,
                      width=DEFAULT_WIDTH, fps=DEFAULT_FPS, speed=DEFAULT_SPEED, crop=None, once=False,
                      report=None, cancel=None):
    """動画の start〜end 秒を、往復ループの GIF にして保存し、保存先を返す
    crop：切り抜く範囲 (x, y, 横幅, 高さ)。None なら切り抜かない（ステップ9）
    once=True：順再生を1回だけ再生して、最後の絵で止まる GIF にする（ステップ25）
    report・cancel：進み具合を知らせる関数と、やめる合図（ステップ32）。どちらもなくてもよい"""
    info = probe(video_path)
    if end is None:
        end = start + DEFAULT_LENGTH
    if info["duration"] > 0:
        end = min(end, info["duration"])  # 動画より長い終了は、動画の最後までにする
    problems = check_settings(start, end, width, fps, speed, info["duration"])
    if crop:
        # 画面の枠は小数で動くので、ピクセル（整数）に直す。四捨五入で 1 ピクセルはみ出さないよう、位置で調整する
        w, h = round(crop[2]), round(crop[3])
        x = min(round(crop[0]), info["width"] - w)
        y = min(round(crop[1]), info["height"] - h)
        crop = (x, y, w, h)
        problems += check_crop(crop, info["width"], info["height"])
    if problems:
        raise FileProblem("\n".join(problems))
    output_path = Path(output_path) if output_path else default_output_path(video_path)

    command = ["ffmpeg", "-hide_banner", "-n",  # -n：同じ名前があれば上書きしない（念のため）
               # 始点もほんの少し手前を指定して、始点の絵が1枚ずれないようにする（ステップ12）
               "-ss", f"{max(0.0, start - SEEK_MARGIN):.6f}", "-t", f"{end - start:.6f}", "-i", str(video_path),
               "-filter_complex", build_filter(width, fps, speed, crop, once, watch=True),
               "-loop", "-1" if once else "0",  # 0：ずっとくり返す、-1：くり返さない（1回だけ）
               str(output_path)]
    existed = output_path.exists()  # もともとあったファイル（-n で上書きしないので、作れずに終わる）
    try:
        code, last_lines = run_watching(command, end - start, estimate_frames(start, end, fps, speed, once),
                                        report, cancel)
    except Cancelled:
        if not existed:  # やめたときは、書きかけの GIF を残さない（このツールが作ったものだけ消す）
            output_path.unlink(missing_ok=True)
        raise
    if code != 0 or not output_path.is_file():
        raise FileProblem(f"GIF を作れませんでした\n{last_lines}")
    return output_path


# ---- ファイルサイズの上限に収める（ステップ10） ----

# 貼り付け先ごとの決まり：（上限 MB, 絵の枚数の上限, 横幅の上限, 高さの上限）。None は決まりなし
# 数字は 2026年11月に、Discord・X の公式の説明などで調べたもの。変わることがあるので「指定サイズ」も用意する
SIZE_PRESETS = {
    "上限なし": (None, None, None, None),
    "Discord 無料（20MB）": (20, None, None, None),
    "Discord（Nitro Basic）（50MB）": (50, None, None, None),
    "Discord Nitro（500MB）": (500, None, None, None),
    "X（15MB）": (15, 350, 1280, 1080),
    "X スマホ（5MB）": (5, 350, 1280, 1080),  # 名前はステップ30でスマホ版にそろえた
    # LINE（トークで送る）：公式の説明では上限が見つからなかった。LINE 以外の会社のまとめページにあった
    # 「トークの画像は 20MB まで」を目安にしている（ステップ15）
    "LINE（目安 20MB）": (20, None, None, None),
    "指定サイズ": ("custom", None, None, None),
}
BYTES_PER_MB = 1000 * 1000  # 1MB を 1,000,000 バイトとして数える（1,048,576 とするより小さいので、安全側）
MIN_AUTO_WIDTH = 160        # 自動で横幅を下げるとき、これより小さくはしない
MIN_AUTO_FPS = 5            # 自動で fps を下げるとき、これより小さくはしない
MAX_TRIES = 8               # 作り直す回数の上限


def output_height(width, crop, video_width, video_height):
    """横幅を決めたときの、GIF の高さ（比率から計算。ffmpeg と同じく偶数にそろえる）"""
    src_w, src_h = (crop[2], crop[3]) if crop else (video_width, video_height)
    return round(width * src_h / src_w / 2) * 2


def apply_platform_rules(start, end, width, fps, speed, crop, info, max_frames, max_w, max_h, once=False):
    """X の「350枚まで」「1280×1080 まで」のような決まりに合わせて、作る前に fps と横幅を下げる
    返すもの：(横幅, fps, 何を変えたかの説明のリスト)"""
    notes = []
    if max_frames:
        seconds = (min(end, info["duration"]) - start) / speed  # GIF の順再生ぶんの長さ
        parts = 1 if once else 2  # 往復なら、順再生と逆再生の2つぶんの枚数になる
        best_fps = int(max_frames / (parts * seconds)) if seconds > 0 else fps
        if best_fps < 1:
            raise FileProblem(f"範囲が長すぎて、絵の枚数を {max_frames} 枚までに収められません。"
                              "範囲を短くするか、再生スピードを上げてください")
        if fps > best_fps:
            notes.append(f"絵の枚数を {max_frames} 枚までにするため、fps を {fps} → {best_fps} に下げました")
            fps = best_fps
    if max_w and max_h:
        new_width = width
        while new_width > MIN_AUTO_WIDTH and (
                new_width > max_w or output_height(new_width, crop, info["width"], info["height"]) > max_h):
            new_width -= 2
        if new_width != width:
            notes.append(f"大きさを {max_w}×{max_h} までにするため、横幅を {width} → {new_width} に下げました")
            width = new_width
    return width, fps, notes


def make_gif_within(video_path, output_path, start, end, width, fps, speed, crop=None,
                    preset="上限なし", custom_mb=None, progress=None, once=False, report=None, cancel=None):
    """上限サイズに収まるまで、横幅 → fps の順に下げて作り直す
    progress：途中のようすを知らせる関数（画面に出すため）。なくてもよい
    once=True：1回だけ再生して止まる GIF（ステップ25）
    report：進み具合を (何回目か, 0〜1) で知らせる関数、cancel：やめる合図（ステップ32）
    返すもの：{"path", "size", "width", "fps", "notes"}"""
    limit_mb, max_frames, max_w, max_h = SIZE_PRESETS[preset]
    if limit_mb == "custom":
        limit_mb = custom_mb
    info = probe(video_path)
    if end is None:
        end = start + DEFAULT_LENGTH
    width, fps, notes = apply_platform_rules(start, end, width, fps, speed, crop, info, max_frames, max_w, max_h,
                                             once)
    output_path = Path(output_path)
    say = progress or (lambda text: None)

    if not limit_mb:  # 上限なし：1回作るだけ
        say("GIF を作っています…")
        make_pingpong_gif(video_path, output_path, start, end, width, fps, speed, crop, once,
                          report and (lambda f: report(1, f)), cancel)
        return {"path": output_path, "size": output_path.stat().st_size, "width": width, "fps": fps, "notes": notes}

    limit = limit_mb * BYTES_PER_MB
    first_width, first_fps = width, fps
    # 作り直しのたびに同じ名前に書けるよう、試しの GIF は別の名前で作り、収まったものだけを本当の名前にする
    # 試しの名前がすでにある（使う人のファイルかもしれない）ときは、番号を付けて別の名前にする
    trial = output_path.with_name(output_path.stem + "_作成中.gif")
    number = 2
    while trial.exists():
        trial = output_path.with_name(f"{output_path.stem}_作成中{number}.gif")
        number += 1
    try:
        for attempt in range(1, MAX_TRIES + 1):
            say(f"GIF を作っています…（{attempt} 回目：横幅 {width}・{fps}fps）")
            if trial.exists():  # 前の回に、このツールが作った試しの GIF
                trial.unlink()
            make_pingpong_gif(video_path, trial, start, end, width, fps, speed, crop, once,
                              report and (lambda f, n=attempt: report(n, f)), cancel)
            size = trial.stat().st_size
            tried = (width, fps)
            if size <= limit:
                trial.rename(output_path)
                changed = []  # 変えたものだけを書く
                if width != first_width:
                    changed.append(f"横幅 {first_width} → {width}")
                if fps != first_fps:
                    changed.append(f"fps {first_fps} → {fps}")
                if changed:
                    notes.append(f"{limit_mb:g}MB に収めるため、{'、'.join(changed)} にして作り直しました"
                                 f"（{attempt} 回目で収まりました）")
                return {"path": output_path, "size": size, "width": width, "fps": fps, "notes": notes}
            # 大きすぎた：まず横幅を下げる。GIF の大きさは、だいたい「横幅×高さ」に比例するので、
            # 上限との比の平方根をかけ、さらに少し余裕（0.9 倍）を見て下げる
            if width > MIN_AUTO_WIDTH:
                width = max(MIN_AUTO_WIDTH, int(width * (limit / size) ** 0.5 * 0.9) // 2 * 2)
            elif fps > MIN_AUTO_FPS:  # 横幅が下げきったら、fps を下げる
                fps = max(MIN_AUTO_FPS, int(fps * 0.75))
            else:
                break
        raise FileProblem(f"横幅 {tried[0]}・{tried[1]}fps まで下げても、{limit_mb:g}MB に収まりませんでした"
                          f"（{size / BYTES_PER_MB:.1f}MB）。範囲を短くしてみてください")
    finally:
        if trial.exists():  # 途中でやめたときも、試しの GIF は残さない
            trial.unlink()


def fit_filter(max_width, max_height, upscale=False):
    """縦横どちらも枠に収まるように、比率を保ったまま縮める指定（もともと小さい絵は、そのまま）
    upscale=True のときは、小さい絵も枠いっぱいまで大きくする（ステップ19：画面を広げたときのプレビュー用）"""
    if upscale:
        return f"scale={max_width}:{max_height}:force_original_aspect_ratio=decrease"
    return (f"scale='min(iw,{max_width})':'min(ih,{max_height})':"
            "force_original_aspect_ratio=decrease")


def ppm_frames(command):
    """ffmpeg に PPM（とても単純な画像の形式）を書き出させ、受け取ったものを1枚ずつに切り分けて返す"""
    try:
        result = subprocess.run(command, capture_output=True, creationflags=NO_WINDOW)
    except FileNotFoundError:
        raise FfmpegMissing("ffmpeg が見つかりません。ffmpeg を入れてから、もう一度試してください")
    return split_ppm(result.stdout)


def video_frame(video_path, seconds, max_width, max_height, upscale=False):
    """動画の seconds 秒の位置の絵を1枚、枠に収まる大きさで取り出す（ステップ8：シークバー用）
    upscale=True なら、小さい動画も枠いっぱいまで拡大する（ステップ19）
    見つからないとき（動画の最後ぎりぎりなど）は None を返す"""
    frames = ppm_frames(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         # -i より前に書くと、その近くまで一気に飛ぶので速い
         # ffmpeg は「指定した時刻より後ろの、最初の絵」を返すので、計算の誤差で1枚先の絵にならないよう、
         # ほんの少し（0.001 秒）手前を指定する（ステップ12）
         "-ss", f"{max(0.0, seconds - SEEK_MARGIN):.6f}",
         "-i", str(video_path), "-an", "-frames:v", "1",
         "-vf", fit_filter(max_width, max_height, upscale),
         "-f", "image2pipe", "-vcodec", "ppm", "-"])
    return frames[0] if frames else None


def preview_frames(gif_path, max_width, max_height):
    """画面の中で再生するための絵を、ffmpeg でまとめて取り出す（ステップ4で速くした）
    ffmpeg は GIF の「変わった部分だけ」を前の絵に重ねて、完成した絵にしてくれる
    返すもの：PPM の中身（bytes）のリスト"""
    return ppm_frames(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(gif_path),
         "-vf", fit_filter(max_width, max_height),
         "-f", "image2pipe", "-vcodec", "ppm", "-"])


def split_ppm(data):
    """つながったまま届いた PPM を、1枚ずつに切り分ける"""
    frames = []
    position = 0
    while position < len(data):
        # PPM の頭の部分は「P6 横幅 高さ 255」のあとに改行が1つ。そのあとに 横幅×高さ×3 バイトの色がならぶ
        parts = []
        cursor = position
        while len(parts) < 4:
            end = cursor
            while end < len(data) and data[end:end + 1] not in (b" ", b"\n"):
                end += 1
            if end >= len(data):  # 途中で切れている（ffmpeg が途中で止まったなど）ときは、そこまでで終わり
                return frames
            parts.append(data[cursor:end])
            cursor = end + 1
        width, height = int(parts[1]), int(parts[2])
        frame_end = cursor + width * height * 3
        if frame_end > len(data):
            return frames
        frames.append(data[position:frame_end])
        position = frame_end
    return frames


def main():
    parser = argparse.ArgumentParser(description="動画を往復ループの GIF にする")
    parser.add_argument("video", help="元の動画ファイル")
    parser.add_argument("--start", type=float, default=DEFAULT_START, help="開始（秒）")
    parser.add_argument("--end", type=float, default=None, help="終了（秒）。省略すると開始から3秒")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="横幅（ピクセル）")
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS, help="1秒に使う絵の枚数")
    parser.add_argument("--speed", type=float, default=DEFAULT_SPEED, help="再生スピード（倍）")
    parser.add_argument("--out", default=None, help="保存先（省略すると元の動画と同じ場所）")
    args = parser.parse_args()
    try:
        saved = make_pingpong_gif(args.video, args.out, args.start, args.end, args.width, args.fps, args.speed)
    except (FfmpegMissing, FileProblem) as error:
        print(f"エラー：{error}")
        sys.exit(1)
    print(f"保存しました：{saved}")


if __name__ == "__main__":
    main()
