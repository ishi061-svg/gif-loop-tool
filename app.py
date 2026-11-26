# GIF ループツール（画面）
# ステップ2：動画を選び、4つの項目（範囲・横幅・fps・スピード）を決めて、往復ループの GIF を作る画面
# ステップ3：できた GIF を、画面の下でくり返し再生して確かめられるようにする
# ステップ4：おかしな入力・重くなりそうなとき・思わぬ失敗に、分かりやすい案内を出す
# ステップ7：動画を画面にドラッグ＆ドロップしても入れられるようにする
# ステップ8：動画の絵を見ながら、シークバーと「ここを始点・ここを終点」で範囲を決められるようにする
# ステップ9：出力比率を選び、動画の上の切り抜き枠を動かしたり大きさを変えたりして、使う部分を決められるようにする
# ステップ10：貼り付け先（Discord・X・指定サイズ）を選び、その上限に収まる GIF を作る
# ステップ12：いまの位置・始点・終点を、動画編集ソフトのように「時:分:秒:フレーム」で表示・入力する
# ステップ13：シークバーの下に「始点へ」「1フレーム前・後ろ」「終点へ」のボタンを付ける
# ステップ14：fps と再生スピードを▲▼ボタンで上下できるようにし、出力比率の位置をほかの欄とそろえる
# ステップ17：タイムをプレビューの下の真ん中に置き、シークバーに始点・終点の縦線、1秒・0.5秒の移動ボタンを付ける
# ステップ18：キーボードの ←→ で1フレーム、Shift＋←→ で1秒ずつ動かせるようにする
# ステップ19：画面を広げたり最大化したりできるようにし、広げたぶん動画の絵とシークバーを大きくする
# ステップ20：動画をドロップできることが分かるよう、点線の枠と案内を出し、ファイルを重ねたら色を変える
# ステップ21：画面の左上とタスクバーに、ツールのアイコン（icon.ico。make_icon.py で作る）を付ける
# ステップ23：［◀1F］［1F▶］の間をあけ、「GIF出力」「出力プレビュー」に名前を変える
# ステップ24：保存せずに確かめる［プレビュー］ボタン。設定が同じなら「GIF出力」はプレビューの GIF をそのまま保存する
# ステップ25：1回だけ再生して止まる GIF を保存する［1回だけ出力］ボタン
# ステップ26：シークバーを拡大・縮小できるようにする（Ctrl＋ホイール、［−］［＋］［全体］ボタン）
# ステップ27：拡大中は横のスクロールバーとホイールで見る場所を動かし、赤い線が外へ出たら自動で追いかける
# ステップ29：始点を終点より後ろに置いたら終点も、終点を始点より前に置いたら始点も、範囲の長さを保ってついてくる
# ステップ30：スマホ版（くるりん GIF）に合わせて、タイムの下に範囲と GIF の長さを出し、ボタンや貼り付け先の名前をそろえる
# ステップ31：再生スピードを 0.25〜4倍の間で 0.05倍きざみに動かせるスライダーを足す（スマホ版と同じ）
# ステップ32：作っている間、進み具合のバーと「あと約○秒」を出し、［やめる］で途中で止められるようにする
# ステップ33：見た目をスマホ版にそろえる（明るい色、①使うところ ②仕上がり ③作って保存 のカード、ボタンで選ぶ比率・貼り付け先）
#
# しくみ
#   - 変換そのものは gif_loop.py（ステップ1）にまかせる
#   - 変換には数秒〜数十秒かかるので、別の作業の流れ（スレッド）で動かし、その間も画面が固まらないようにする
#
# 必要なもの：ffmpeg、tkinterdnd2（ドラッグ＆ドロップ用。入れ方：python -m pip install tkinterdnd2）
#
# 使い方（確認用）
#   python app.py

import ctypes
import math
import shutil
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD  # ドラッグ＆ドロップを受け取るための追加の部品

import gif_loop

# 全角の数字や記号（１．５ など）を、半角（1.5）に直すための対応表
ZENKAKU_TO_HANKAKU = str.maketrans("０１２３４５６７８９．－：", "0123456789.-:")
VIEW_W, VIEW_H = 480, 270          # 動画の絵を見せる場所の大きさ（ピクセル）
SEEK_H = 40                        # シークバーの高さ（ステップ33で、つかみやすく高くした）
SEEK_PAD = 10                      # シークバーの左右のすきま
MIN_SPAN_FRAMES = 20               # シークバーをいちばん拡大したときに見えるフレーム数（ステップ26）
GIF_VIEW_W, GIF_VIEW_H = 480, 480  # できた GIF を再生する場所の大きさ。縦長の GIF も入るよう正方形にする
# 出力比率（ステップ9）。数字は 横:縦。None は切り抜かない
RATIOS = {"元のまま": None, "1:1": (1, 1), "16:9": (16, 9), "9:16": (9, 16), "4:3": (4, 3), "3:4": (3, 4)}
RATIO_NAMES = list(RATIOS)
PRESET_NAMES = list(gif_loop.SIZE_PRESETS)  # サイズ上限の選択肢（ステップ10）
HANDLE = 5          # 枠の角の四角の大きさ（半分。ピクセル）
GRAB = 10           # 角をつかんだとみなす近さ（ピクセル）
MIN_CROP = 32       # 切り抜く範囲の、いちばん小さい大きさ（元の動画のピクセル）
VIDEO_TYPES =[("動画ファイル", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"), ("すべてのファイル", "*.*")]

# ---- 見た目（ステップ33）：スマホ版（くるりん GIF）と同じ色 ----
BG, SURFACE, SUNKEN, LINE = "#eef1f5", "#ffffff", "#e4e8ee", "#d3dae4"  # 背景・カード・へこみ・線
INK, SUB, WARN = "#1d2433", "#5d6676", "#9a5b00"                      # 文字・うすい文字・案内
ACCENT, ACCENT_DARK, HOVER = "#2f5fd0", "#244caa", "#f3f6fb"           # 青・押したときの青・マウスを乗せたとき
START, END = "#14833b", "#c2410c"                                      # 始点（緑）・終点（オレンジ）
VIEW_BG = "#1d2433"                                                    # 動画の絵のまわり
FONT = ("Yu Gothic UI", 10)
BOLD_FONT = ("Yu Gothic UI", 11, "bold")
TIME_FONT = ("Consolas", 14)
MONO_FONT = ("Consolas", 11)


def flat_button(parent, text, command, kind="normal", small=False, big=False):
    """平らなボタン（ステップ33）。kind："normal"（白）・"accent"（青）・"outline"（青い文字）・"start"・"end"
    big=True は ③ の大きいボタン、small=True は拡大・縮小などの小さいボタン"""
    colors = {"normal": (SURFACE, INK), "accent": (ACCENT, "#ffffff"), "outline": (SURFACE, ACCENT),
              "start": (SURFACE, START), "end": (SURFACE, END)}[kind]
    # Windows では、ボタンの枠の色を変えられないので、線の色の Frame で包んで 1 ピクセルの枠に見せる
    border = {"accent": ACCENT, "outline": "#9fb6ea", "start": "#9fd3b0", "end": "#f0b896"}.get(kind, LINE)
    wrap = tk.Frame(parent, bg=border, padx=1, pady=1)
    button = tk.Button(wrap, text=text, command=command, bg=colors[0], fg=colors[1], relief="flat", bd=0,
                       highlightthickness=0,
                       activebackground=ACCENT_DARK if kind == "accent" else HOVER,
                       activeforeground=colors[1], disabledforeground="#a8b0bd", cursor="hand2",
                       padx=6 if small else 10, pady=8 if big else (1 if small else 3),
                       font=BOLD_FONT if big or kind in ("start", "end") else FONT)
    button.pack(fill="both", expand=True)
    # 置き方の命令（pack・grid）は、包んでいる Frame にかける。ほかの命令（config など）はボタンにかかる
    button.pack, button.grid, button.pack_forget = wrap.pack, wrap.grid, wrap.pack_forget
    return button


def card(parent, number, title):
    """番号つきの白いカード（ステップ33）。中身は、返したカードに続けて pack する"""
    box = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=LINE, padx=16, pady=12)
    box.pack(fill="x", pady=(12, 0))
    head = tk.Frame(box, bg=SURFACE)
    head.pack(anchor="w", pady=(0, 6))
    mark = tk.Canvas(head, width=26, height=26, bg=SURFACE, highlightthickness=0)
    mark.create_oval(1, 1, 25, 25, fill="#e3eaf9", outline="")
    mark.create_text(13, 13, text=str(number), fill=ACCENT, font=("Yu Gothic UI", 10, "bold"))
    mark.pack(side="left")
    tk.Label(head, text=title, bg=SURFACE, fg=INK, font=BOLD_FONT).pack(side="left", padx=(8, 0))
    return box


def setting_row(parent, title):
    """カードの中の1段（左に項目の名前）。中身は返した段に pack する"""
    row = tk.Frame(parent, bg=SURFACE)
    row.pack(fill="x", pady=(8, 0))
    tk.Label(row, text=title, bg=SURFACE, fg=INK, width=10, anchor="w").pack(side="left")
    return row


def entry(parent, var, width, mono=False):
    """入力欄（ステップ33）。うすい灰色の地に細い枠。入力中は青い枠になる"""
    return tk.Entry(parent, textvariable=var, width=width, justify="right", relief="flat", bg="#f7f9fc",
                    fg=INK, highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
                    disabledbackground=SUNKEN, font=MONO_FONT if mono else FONT)


def spinbox(parent, var, value_range, step, form):
    """▲▼ボタンつきの入力欄（ステップ14）"""
    value = var.get()  # Spinbox を作ると中身が「いちばん小さい値」に変わるので、先に覚えておく
    box = tk.Spinbox(parent, textvariable=var, from_=value_range[0], to=value_range[1], increment=step,
                     format=form, width=6, justify="right", relief="flat", bg="#f7f9fc", fg=INK,
                     buttonbackground=SUNKEN, highlightthickness=1, highlightbackground=LINE,
                     highlightcolor=ACCENT, font=FONT)
    var.set(value)
    return box


def segment(parent, var, items, command, columns=None):
    """スマホ版と同じ「並んだボタンから1つ選ぶ」部品（ステップ33）
    items：(入れ物に入れる値, ボタンの文字) のリスト。選んだボタンは白地に青い文字になる
    columns を決めると、その数で折り返して並べる（貼り付け先のタイル）
    返すもの：ボタンのリスト（入れ物の Frame は buttons[0].master）"""
    frame = tk.Frame(parent, bg=SUNKEN, padx=3, pady=3)
    buttons = []

    def refresh(*_):
        for button, (value, _label) in zip(buttons, items):
            on = var.get() == value
            button.config(bg=SURFACE if on else SUNKEN, fg=ACCENT if on else SUB,
                          font=("Yu Gothic UI", 10, "bold") if on else FONT)

    def choose(value):
        var.set(value)
        command()

    for i, (value, label) in enumerate(items):
        button = tk.Button(frame, text=label, command=lambda v=value: choose(v), relief="flat", bd=0,
                           bg=SUNKEN, fg=SUB, activebackground=SURFACE, activeforeground=ACCENT,
                           disabledforeground="#a8b0bd", cursor="hand2", padx=10,
                           pady=4 if columns else 3, justify="center", highlightthickness=0)
        if columns:
            button.grid(row=i // columns, column=i % columns, sticky="nsew", padx=1, pady=1)
            frame.columnconfigure(i % columns, weight=1, uniform="tile")
        else:
            button.pack(side="left", padx=1)
        buttons.append(button)
    var.trace_add("write", refresh)
    refresh()
    return buttons


def tile_text(name):
    """貼り付け先の名前を、タイルの2行の文字にする（例：「X スマホ（5MB）」→「X スマホ」と「5MB」）"""
    if name == "指定サイズ":
        return "指定サイズ\nMB を入れる"
    if name.endswith("）") and "（" in name:
        cut = name.rindex("（")
        return f"{name[:cut]}\n{name[cut + 1:-1]}"
    return "上限なし\n—" if name == "上限なし" else name


class App:
    def __init__(self, root):
        self.root = root
        self.video_path = None
        self.duration = 0.0  # 選んだ動画の長さ（秒）
        self.converting = False  # GIF を作っている途中かどうか
        root.title("GIF ループツール")
        # 見た目（ステップ33）：スマホ版（くるりん GIF）と同じ明るい色。設定は「①使うところ ②仕上がり ③作って保存」の
        # 白いカードに分け、上から順に進めば GIF ができる並びにする
        root.configure(bg=BG)
        root.option_add("*Font", FONT)
        style = ttk.Style(root)
        style.theme_use("clam")  # 色を変えられる見た目（ttk の部品は、進み具合のバーとスライダーだけ）
        style.configure("Accent.Horizontal.TProgressbar", troughcolor=SUNKEN, background=ACCENT,
                        bordercolor=SUNKEN, lightcolor=ACCENT, darkcolor=ACCENT, thickness=10)
        style.configure("Speed.Horizontal.TScale", troughcolor=SUNKEN, background=ACCENT, gripcount=0,
                        bordercolor=LINE, lightcolor=ACCENT, darkcolor=ACCENT, sliderlength=20, sliderthickness=18)
        style.map("Speed.Horizontal.TScale", background=[("active", ACCENT_DARK)])

        # いちばん上：［動画を選ぶ］と、選んだ動画の名前（ツールの名前は窓の上の帯に出ているので、画面には書かない）
        header = tk.Frame(root, bg=BG, padx=20, pady=12)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        flat_button(header, "動画を選ぶ", self.choose_video, kind="outline").pack(side="left")
        self.file_label = tk.Label(header, text="まだ選んでいません（画面にドロップしても入れられます）",
                                   bg=BG, fg=SUB, anchor="w")
        self.file_label.pack(side="left", padx=(12, 0))

        # 画面を左右に分ける（ステップ8）。左：動画と①②、右：できた GIF と③
        # 画面を広げたときは、左（動画とシークバー）だけが広がる（ステップ19）
        left = tk.Frame(root, bg=BG, padx=20)
        left.grid(row=1, column=0, sticky="nsew", pady=(0, 20))
        right = tk.Frame(root, bg=BG, padx=20)
        right.grid(row=1, column=1, sticky="n", pady=(0, 20))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        self.view_w, self.view_h = VIEW_W, VIEW_H  # 動画の絵を見せる場所の、いまの大きさ（画面を広げると変わる）
        self.seek_w = VIEW_W                       # シークバーの、いまの長さ
        self.resize_job = None                     # 広げ終わってから絵を取り出し直す予約

        # 動画の絵（ステップ8）。あとで切り抜き枠も重ねて描くので、Canvas（自由に描ける部品）にする
        # 画面を広げると、あまった場所はこの絵の場所に回す（expand）（ステップ19）
        self.view = tk.Canvas(left, width=VIEW_W, height=VIEW_H, bg=VIEW_BG, highlightthickness=0)
        self.view.pack(fill="both", expand=True)
        self.view.bind("<Configure>", self.on_view_resize)
        self.view_image = None    # いま見せている絵（消えないように持っておく）
        self.drop_over = False    # ファイルを画面の上に持ってきている途中か（ステップ20）
        self.drop_leave_job = None  # 「ファイルが離れた」ときの、表示を戻す予約
        self.position = 0.0       # シークバーで選んでいる位置（秒）
        self.frame_rate = gif_loop.DEFAULT_FRAME_RATE  # 動画の 1秒あたりのフレーム数（ステップ12）
        self.frame_busy = False   # 絵を取り出している途中か
        self.frame_wanted = None  # 取り出し中にシークバーが動いたら、次に取り出す位置

        # いまのタイム：プレビューの真ん中にそろえて、すぐ下に置く（ステップ17）
        # 同じ段の左に「見えている範囲」、右に拡大・縮小のボタンを置く（ステップ26）
        # 左右の列を同じ幅（uniform）にして、タイムがプレビューの真ん中からずれないようにする
        time_row = tk.Frame(left, bg=BG)
        time_row.pack(fill="x", pady=(8, 0))
        time_row.columnconfigure(0, weight=1, uniform="side")
        time_row.columnconfigure(2, weight=1, uniform="side")
        self.zoom_label = tk.Label(time_row, text="", bg=BG, fg=SUB, anchor="w")
        self.zoom_label.grid(row=0, column=0, sticky="w")
        self.time_label = tk.Label(time_row, text="00:00:00:00 / 00:00:00:00", bg=BG, fg=INK,
                                   font=TIME_FONT)  # 数字の幅がそろう文字で、タイムが左右にぶれないようにする
        self.time_label.grid(row=0, column=1)
        zoom_buttons = tk.Frame(time_row, bg=BG)
        zoom_buttons.grid(row=0, column=2, sticky="e")
        self.zoom_start, self.zoom_end = 0.0, 0.0  # シークバーに見えている範囲（秒）。拡大していなければ動画全体
        zoom_list = []
        for text, command in (("−", lambda: self.zoom_by(0.5)), ("＋", lambda: self.zoom_by(2.0)),
                              ("全体", self.zoom_all)):
            button = flat_button(zoom_buttons, text, command, small=True)
            button.config(state="disabled")
            button.pack(side="left", padx=(4, 0))
            zoom_list.append(button)
        # タイムのすぐ下：範囲の長さと、できる GIF の長さ（往復・片道）（ステップ30）
        self.length_label = tk.Label(left, text="範囲 —｜GIF 往復 —・片道 —", bg=BG, fg=SUB)
        self.length_label.pack()

        # ① 使うところを決める
        card1 = card(left, 1, "使うところを決める")
        # シークバー：横線の上に、使う範囲（青）、始点（緑）・終点（オレンジ）の縦線、いまの位置（青い丸）を描く
        self.seek = tk.Canvas(card1, width=VIEW_W, height=SEEK_H, bg=SURFACE, highlightthickness=0, cursor="hand2")
        self.seek.pack(fill="x")  # 横にだけ伸びる（ステップ19）
        self.seek.bind("<Configure>", self.on_seek_resize)
        self.seek.bind("<Button-1>", self.on_seek)
        self.seek.bind("<B1-Motion>", self.on_seek)
        self.seek.bind("<Control-MouseWheel>", self.on_seek_ctrl_wheel)  # Ctrl＋ホイールで拡大・縮小（ステップ26）
        self.seek.bind("<MouseWheel>", self.on_seek_wheel)  # Ctrl なしのホイールで、見る場所を横に動かす（ステップ27）

        # 拡大しているときだけ出す、横のスクロールバー（ステップ27）
        # 出したり消したりで画面がガタつかないよう、高さの決まった入れ物を先に置いておき、その中に出し入れする
        scroll_box = tk.Frame(card1, height=16, bg=SURFACE)
        scroll_box.pack(fill="x")
        scroll_box.pack_propagate(False)
        self.scrollbar = tk.Scrollbar(scroll_box, orient="horizontal", command=self.on_scrollbar)
        self.scrollbar.bind("<MouseWheel>", self.on_seek_wheel)

        # シークバーの操作ボタン（ステップ13・17）
        # 左端に「始点へ」、右端に「終点へ」。真ん中に［始点］1秒・0.5秒・1フレームの移動［終点］
        nav_row = tk.Frame(card1, bg=SURFACE)
        nav_row.pack(fill="x")
        nav_row.columnconfigure(1, weight=1)  # 真ん中の列が広がって、左右のボタンが端に寄る
        self.nav_buttons = [
            flat_button(nav_row, "⏮ 始点へ", self.go_start),
            flat_button(nav_row, "終点へ ⏭", self.go_end),
        ]
        self.nav_buttons[0].grid(row=0, column=0, sticky="w")
        self.nav_buttons[1].grid(row=0, column=2, sticky="e")
        middle = tk.Frame(nav_row, bg=SURFACE)
        middle.grid(row=0, column=1)
        self.start_button = flat_button(middle, "始点", self.set_start_here, kind="start")
        self.start_button.pack(side="left", padx=(0, 8))
        # （ボタンの文字, 動く秒数, フレーム単位か）
        steps = [("◀1秒", -1.0, False), ("◀0.5秒", -0.5, False), ("◀1F", -1, True),
                 ("1F▶", 1, True), ("0.5秒▶", 0.5, False), ("1秒▶", 1.0, False)]
        for text, amount, is_frame in steps:
            command = (lambda a=amount: self.step_frame(a)) if is_frame else (lambda a=amount: self.step_seconds(a))
            button = flat_button(middle, text, command)
            # ［◀1F］と［1F▶］の間だけ広くあけて、押しまちがえにくくする（ステップ23）
            button.pack(side="left", padx=(14, 2) if text == "1F▶" else 2)
            self.nav_buttons.append(button)
        self.end_button = flat_button(middle, "終点", self.set_end_here, kind="end")
        self.end_button.pack(side="left", padx=(8, 0))
        for button in self.nav_buttons + [self.start_button, self.end_button]:
            button.config(state="disabled")
        self.nav_buttons += zoom_list  # 拡大・縮小のボタンも、動画を入れたら押せるようにする（ステップ26）

        # 始点・終点は「時:分:秒:フレーム」で入れる（ステップ12）（StringVar：画面の文字と結びついた入れ物）
        self.start_var = tk.StringVar(value=self.timecode(gif_loop.DEFAULT_START))
        self.end_var = tk.StringVar(value=self.timecode(gif_loop.DEFAULT_START + gif_loop.DEFAULT_LENGTH))
        self.width_var = tk.StringVar(value=str(gif_loop.DEFAULT_WIDTH))
        self.fps_var = tk.StringVar(value=str(gif_loop.DEFAULT_FPS))
        self.speed_var = tk.StringVar(value=f"{gif_loop.DEFAULT_SPEED:.2f}")

        range_line = setting_row(card1, "使う範囲")
        entry(range_line, self.start_var, 12, mono=True).pack(side="left")
        tk.Label(range_line, text="から", bg=SURFACE, fg=SUB).pack(side="left", padx=(6, 12))
        entry(range_line, self.end_var, 12, mono=True).pack(side="left")
        tk.Label(range_line, text="まで", bg=SURFACE, fg=SUB).pack(side="left", padx=(6, 0))

        # 出力比率と切り抜き枠（ステップ9）。スマホ版と同じく、並んだボタンから選ぶ（ステップ33）
        ratio_line = setting_row(card1, "出力比率")
        self.ratio_var = tk.StringVar(value=RATIO_NAMES[0])
        self.ratio_buttons = segment(ratio_line, self.ratio_var, [(name, name) for name in RATIO_NAMES],
                                     self.on_ratio)
        self.ratio_buttons[0].master.pack(side="left")
        for button in self.ratio_buttons:
            button.config(state="disabled")
        self.crop_label = tk.Label(ratio_line, text="", bg=SURFACE, fg=SUB, anchor="w")
        self.crop_label.pack(side="left", padx=(12, 0))
        self.video_size = (0, 0)  # 元の動画の横幅・高さ（ピクセル）
        self.crop = None          # 切り抜く範囲 [x, y, 横幅, 高さ]（元の動画のピクセル）。None は切り抜かない
        self.drag = None          # 枠をドラッグしている途中の情報
        self.view.bind("<Button-1>", self.on_view_press)
        self.view.bind("<B1-Motion>", self.on_view_drag)
        self.view.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))
        self.view.bind("<Motion>", self.on_view_hover)

        # ② 仕上がりを選ぶ
        card2 = card(left, 2, "仕上がりを選ぶ")
        # ▲▼ボタンで上下できる欄（ステップ14）。スピードは 0.05倍きざみも見えるよう小数2けた（ステップ31）
        speed_line = setting_row(card2, "再生スピード")
        spinbox(speed_line, self.speed_var, gif_loop.SPEED_RANGE, 0.1, "%.2f").pack(side="left")
        tk.Label(speed_line, text="倍", bg=SURFACE, fg=SUB).pack(side="left", padx=(6, 14))
        self.add_speed_slider(speed_line)
        fps_line = setting_row(card2, "なめらかさ")
        spinbox(fps_line, self.fps_var, gif_loop.FPS_RANGE, 1, "%.0f").pack(side="left")
        tk.Label(fps_line, text="fps（1秒に使う絵の枚数）", bg=SURFACE, fg=SUB).pack(side="left", padx=(6, 0))
        width_line = setting_row(card2, "横幅")
        entry(width_line, self.width_var, 7).pack(side="left")
        tk.Label(width_line, text="ピクセル（縦は自動）", bg=SURFACE, fg=SUB).pack(side="left", padx=(6, 0))

        # サイズの上限（ステップ10）：貼り付け先を、スマホ版と同じくボタンの並びから選ぶ（ステップ33）
        # 「指定サイズ」のときだけ MB の欄を使える
        tk.Label(card2, text="貼り付け先（サイズの上限）", bg=SURFACE, fg=INK).pack(anchor="w", pady=(10, 4))
        self.preset_var = tk.StringVar(value=PRESET_NAMES[0])
        self.preset_buttons = segment(card2, self.preset_var, [(name, tile_text(name)) for name in PRESET_NAMES],
                                      self.on_preset, columns=4)
        self.preset_buttons[0].master.pack(fill="x")
        mb_line = tk.Frame(card2, bg=SURFACE)
        mb_line.pack(anchor="w", pady=(6, 0))
        tk.Label(mb_line, text="指定サイズ：", bg=SURFACE, fg=SUB).pack(side="left")
        self.custom_mb_var = tk.StringVar(value="10")
        self.custom_mb_entry = entry(mb_line, self.custom_mb_var, 6)
        self.custom_mb_entry.config(state="disabled")
        self.custom_mb_entry.pack(side="left")
        tk.Label(mb_line, text="MB", bg=SURFACE, fg=SUB).pack(side="left", padx=(6, 0))

        # 右：できた GIF を再生する場所（ステップ3）
        tk.Label(right, text="出力プレビュー", bg=BG, fg=INK, font=BOLD_FONT).pack(anchor="w")  # 名前はステップ23で変更
        gif_area = tk.Frame(right, width=GIF_VIEW_W, height=GIF_VIEW_H, bg=SUNKEN)
        gif_area.pack(pady=(6, 0))
        gif_area.pack_propagate(False)  # 中身の大きさで場所が伸び縮みしないようにする
        self.preview_label = tk.Label(gif_area, bg=SUNKEN, text="ここで再生されます", fg=SUB)
        self.preview_label.pack(expand=True)
        self.preview_frames = []   # GIF の1枚1枚の絵
        self.preview_index = 0     # いま見せている絵の番号
        self.preview_delay = 66    # 次の絵までの時間（ミリ秒）
        self.preview_job = None    # 次の絵に進む予約（新しい GIF を見せるときに取り消す）
        self.preview_once = False  # 1回だけ再生して止める GIF か（ステップ25）
        self.preview_label.bind("<Button-1>", self.replay_preview)
        # できた GIF の大きさと、自動で変えたことの説明（ステップ10）
        self.result_label = tk.Label(right, text="", bg=BG, fg=INK, anchor="w", justify="left",
                                     wraplength=GIF_VIEW_W)
        self.result_label.pack(fill="x", pady=(6, 0))

        # ③ 作って保存する：［プレビュー］［往復 GIF を保存］［往復しない GIF を保存］（ステップ24・25・30）
        card3 = card(right, 3, "作って保存する")
        self.preview_button = flat_button(card3, "プレビュー（保存しない）", self.preview_gif, big=True)
        self.preview_button.pack(fill="x")
        self.make_button = flat_button(card3, "往復 GIF を保存", self.make_gif, kind="accent", big=True)
        self.make_button.pack(fill="x", pady=(8, 0))
        self.once_button = flat_button(card3, "往復しない GIF を保存", self.make_once_gif, big=True)
        self.once_button.pack(fill="x", pady=(8, 0))
        for button in (self.preview_button, self.make_button, self.once_button):
            button.config(state="disabled")
        # 作っている間だけ出す、進み具合のバーと［やめる］ボタン（ステップ32）
        # 出したり消したりで画面がガタつかないよう、高さの決まった入れ物を先に置いておき、その中に出し入れする
        self.progress_box = tk.Frame(card3, height=34, bg=SURFACE)
        self.progress_box.pack(fill="x", pady=(10, 0))
        self.progress_box.pack_propagate(False)
        self.progress_bar = ttk.Progressbar(self.progress_box, maximum=100, style="Accent.Horizontal.TProgressbar")
        self.cancel_button = flat_button(self.progress_box, "やめる", self.cancel_convert)
        self.cancel_event = None    # やめる合図（作り始めるたびに新しく作る）
        self.progress_base = ""     # 「GIF を作っています（2 回目…）」など、いまの作業の説明
        self.attempt = 0            # サイズ上限に収めるために、何回目を作っているか
        self.attempt_started = 0.0  # その回を始めた時刻（あと何秒かの計算に使う）
        # いまの状態
        self.status_label = tk.Label(card3, text="動画を選んでください", bg=SURFACE, fg=WARN, anchor="w",
                                     justify="left", wraplength=GIF_VIEW_W - 40)
        self.status_label.pack(fill="x", pady=(4, 0))
        self.last_preview = None  # 最後に作ったプレビュー {"key": 設定の目印, "result": 結果}
        self.temp_dir = None      # プレビュー用の一時フォルダ（最初のプレビューのときに作る）
        self.preview_count = 0    # プレビューの GIF に付ける番号
        root.protocol("WM_DELETE_WINDOW", self.on_close)  # 閉じるときに一時フォルダを片づける

        # 開始・終了の欄を書きかえたら、シークバーの青い範囲も描き直す
        # 「始点が終点より後ろ」の案内も、そのたびに見直す
        self.start_var.trace_add("write", lambda *_: self.on_range_changed())
        self.end_var.trace_add("write", lambda *_: self.on_range_changed())
        # fps・スピードが変わると GIF の長さも変わるので、長さの表示を直す（ステップ30）
        self.fps_var.trace_add("write", lambda *_: self.update_length())
        self.speed_var.trace_add("write", lambda *_: self.update_length())
        self.draw_seek()
        self.update_length()

        # キーボードで位置を動かす（ステップ18）：←→ で1フレーム、Shift を押しながら ←→ で1秒
        root.bind("<Left>", lambda e: self.on_arrow_key(e, -1, False))
        root.bind("<Right>", lambda e: self.on_arrow_key(e, 1, False))
        root.bind("<Shift-Left>", lambda e: self.on_arrow_key(e, -1, True))
        root.bind("<Shift-Right>", lambda e: self.on_arrow_key(e, 1, True))

        # 画面のどこにドロップしても受け取れるようにする（ステップ7）
        # ドラッグ＆ドロップの部品なしで作った画面（確認用のテストなど）では、何もしない
        if hasattr(root, "drop_target_register"):
            self.register_drop(root)

        # 最初の大きさより小さくはできないようにする。ボタンや欄が隠れないようにするため（ステップ19）
        root.update_idletasks()
        root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())

    def register_drop(self, widget):
        """この部品と、その中の部品すべてを、ドロップを受け取る場所にする"""
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", self.on_drop)
        widget.dnd_bind("<<DropEnter>>", self.on_drop_enter)  # ファイルを画面の上に持ってきた（ステップ20）
        widget.dnd_bind("<<DropLeave>>", self.on_drop_leave)  # ファイルが画面の外へ出た
        for child in widget.winfo_children():
            self.register_drop(child)

    # ---- ドロップできることを見せる（ステップ20） ----

    def draw_drop_hint(self):
        """動画の場所に、ドロップの案内を描く
        - 動画を入れる前：点線の枠と「ここに動画をドロップ」
        - ファイルを画面の上に持ってきている間：枠を青くして「離すと読み込みます」"""
        c = self.view
        c.delete("hint")
        if self.video_path and not self.drop_over:
            return  # 動画を見ているときは、じゃまをしない
        w, h, pad = self.view_w, self.view_h, 14
        color = "#60a5fa" if self.drop_over else "#8a8a8a"
        if self.video_path:
            # 動画の上に重ねるときは、絵を半分だけ青くして、上に案内を出す
            c.create_rectangle(0, 0, w, h, fill="#1e40af", stipple="gray50", outline="", tags="hint")
        elif self.drop_over:
            c.create_rectangle(pad, pad, w - pad, h - pad, fill="#1e3a8a", outline="", tags="hint")
        c.create_rectangle(pad, pad, w - pad, h - pad, outline=color, width=3, dash=(10, 6), tags="hint")
        title = "離すと読み込みます" if self.drop_over else "ここに動画をドロップ"
        sub = ("別の動画に入れかえます" if self.video_path else "MP4・MOV などの動画ファイル") if self.drop_over \
            else "または、左上の「動画を選ぶ」から選べます"
        if self.video_path:
            # 動画の絵の上だと文字が読みにくいので、文字の後ろに濃い青の帯を敷く
            c.create_rectangle(w // 2 - 170, h // 2 - 46, w // 2 + 170, h // 2 + 42,
                               fill="#1e3a8a", outline=color, width=2, tags="hint")
        c.create_text(w // 2, h // 2 - 14, text=title, fill="white" if self.drop_over else "#d0d0d0",
                      font=("Meiryo UI", 20, "bold"), tags="hint")
        c.create_text(w // 2, h // 2 + 22, text=sub, fill="#dbeafe" if self.drop_over else "#9a9a9a",
                      font=("Meiryo UI", 10), tags="hint")

    def on_drop_enter(self, event):
        # 画面の中で部品から部品へ移るときも「離れた→入った」が届くので、戻す予約を取り消す
        if self.drop_leave_job:
            self.root.after_cancel(self.drop_leave_job)
            self.drop_leave_job = None
        if not self.drop_over:
            self.drop_over = True
            self.draw_drop_hint()
        return event.action

    def on_drop_leave(self, event):
        # すぐ戻すと、部品から部品へ移るたびに色がちらつくので、少し待ってから戻す
        if self.drop_leave_job:
            self.root.after_cancel(self.drop_leave_job)
        self.drop_leave_job = self.root.after(100, self.end_drop_over)
        return event.action

    def end_drop_over(self):
        self.drop_leave_job = None
        self.drop_over = False
        self.draw_drop_hint()

    def on_drop(self, event):
        """ドロップされたファイルを読み込む。GIF は1つずつ作るので、複数のときは最初の1つだけ使う"""
        if self.drop_leave_job:
            self.root.after_cancel(self.drop_leave_job)
        self.end_drop_over()  # 落とし終わったので、青い表示を戻す
        # 落とされたものの一覧は1つの文字列で届く。空白を含む名前は { } で囲まれているので、splitlist で分ける
        paths = self.root.tk.splitlist(event.data)
        if not paths:
            return
        if self.converting:
            messagebox.showinfo("作っている途中です", "GIF を作り終わってから、次の動画を入れてください")
            return
        if len(paths) > 1:
            messagebox.showinfo("1つずつ入れてください", f"複数のファイルが入れられたので、最初の1つ（{Path(paths[0]).name}）を使います")
        self.load_video(paths[0])

    def choose_video(self):
        path = filedialog.askopenfilename(title="動画を選ぶ", filetypes=VIDEO_TYPES)
        if path:
            self.load_video(path)

    def load_video(self, path):
        """動画を読み込み、長さを表示する。終了の初期値は「開始から3秒」か「動画の最後」の短いほう"""
        try:
            info = gif_loop.probe(path)
        except (gif_loop.FfmpegMissing, gif_loop.FileProblem) as error:
            messagebox.showerror("読み込めません", str(error))
            return
        self.video_path = Path(path)
        self.draw_drop_hint()  # 「ここに動画をドロップ」を消す（ステップ20）
        self.duration = info["duration"]
        self.file_label.config(text=f"{self.video_path.name}（長さ {info['duration']:.1f} 秒）")
        self.video_size = (info["width"], info["height"])
        for button in self.ratio_buttons:  # 比率のボタンを押せるようにする（ステップ33）
            button.config(state="normal")
        self.on_ratio()  # 選んでいる比率の枠を、新しい動画に合わせて作り直す
        end = min(gif_loop.DEFAULT_START + gif_loop.DEFAULT_LENGTH, info["duration"]) if info["duration"] else 3.0
        self.frame_rate = info["frame_rate"]
        self.zoom_start, self.zoom_end = 0.0, self.duration  # 新しい動画は、全体を見せるところから（ステップ26）
        self.update_zoom_label()
        self.start_var.set(self.timecode(gif_loop.DEFAULT_START))
        self.end_var.set(self.timecode(end))
        self.make_button.config(state="normal")
        self.preview_button.config(state="normal")
        self.once_button.config(state="normal")
        self.start_button.config(state="normal")
        self.end_button.config(state="normal")
        for button in self.nav_buttons:
            button.config(state="normal")
        self.status_label.config(text="項目を決めて「往復 GIF を保存」を押してください")
        self.set_position(0.0)

    # ---- シークバーと動画の絵（ステップ8） ----

    def time_to_x(self, seconds):
        """秒 → シークバーの横の位置（ピクセル）
        シークバーの左端が zoom_start、右端が zoom_end（拡大していなければ 0 秒と動画の最後。ステップ26）"""
        span = self.zoom_end - self.zoom_start
        if not self.duration or span <= 0:
            return SEEK_PAD
        ratio = min(max((seconds - self.zoom_start) / span, 0.0), 1.0)
        return SEEK_PAD + ratio * (self.seek_w - SEEK_PAD * 2)

    def x_to_time(self, x):
        """シークバーの横の位置（ピクセル） → 秒"""
        ratio = (x - SEEK_PAD) / (self.seek_w - SEEK_PAD * 2)
        return self.zoom_start + min(max(ratio, 0.0), 1.0) * (self.zoom_end - self.zoom_start)

    def in_view(self, seconds):
        """その時刻が、いまシークバーに見えている範囲の中にあるか"""
        return self.zoom_start - 1e-9 <= seconds <= self.zoom_end + 1e-9

    # ---- シークバーの拡大・縮小（ステップ26） ----

    def min_span(self):
        """いちばん拡大したときに見える長さ：20フレームぶん（これ以上拡大しても、合わせやすさは変わらない）"""
        return min(self.duration, MIN_SPAN_FRAMES / self.frame_rate)

    def zoom_by(self, factor, center=None, anchor=None):
        """factor 倍に拡大（2.0）・縮小（0.5）する
        center：中心にする時刻（ボタンのときは赤い線＝いまの位置）
        anchor：center がシークバーのどこ（0〜1）に残るか。マウスの位置で拡大したとき、マウスの下の時刻が動かないようにする"""
        if not self.duration:
            return
        if center is None:
            center, anchor = self.position, 0.5
        span = min(max((self.zoom_end - self.zoom_start) / factor, self.min_span()), self.duration)
        start = center - anchor * span
        start = min(max(start, 0.0), self.duration - span)  # 動画の外は見せない
        self.zoom_start, self.zoom_end = start, start + span
        self.update_zoom_label()
        self.draw_seek()

    def zoom_all(self):
        """［全体］：動画の最初から最後までを見せる"""
        self.zoom_start, self.zoom_end = 0.0, self.duration
        self.update_zoom_label()
        self.draw_seek()

    # ---- 拡大中に、見る場所を動かす（ステップ27） ----

    def scroll_to(self, start):
        """見えている範囲の左端を start 秒にする（長さはそのまま。動画の外は見せない）"""
        span = self.zoom_end - self.zoom_start
        start = min(max(start, 0.0), self.duration - span)
        self.zoom_start, self.zoom_end = start, start + span
        self.update_zoom_label()
        self.draw_seek()

    def on_scrollbar(self, action, amount, unit=None):
        """スクロールバーを動かしたとき。tkinter から次のどちらかの形で届く
        - ("moveto", 割合)：つまみをドラッグした → 左端を「動画全体のその割合」の位置にする
        - ("scroll", 回数, "units" か "pages")：左右の矢印か、つまみの外をクリックした"""
        span = self.zoom_end - self.zoom_start
        if action == "moveto":
            self.scroll_to(float(amount) * self.duration)
        elif action == "scroll":
            step = span * (0.1 if unit == "units" else 0.9)  # 矢印は少し、つまみの外は1画面ぶん近く動かす
            self.scroll_to(self.zoom_start + int(amount) * step)

    def on_seek_wheel(self, event):
        """Ctrl なしのホイール：拡大しているときだけ、見る場所を横に動かす（奥へ回すと前、手前で後ろ）"""
        if self.duration and self.zoom_end - self.zoom_start < self.duration - 1e-6:
            self.scroll_to(self.zoom_start - (event.delta / 120) * (self.zoom_end - self.zoom_start) * 0.1)

    def follow_position(self):
        """赤い線（いまの位置）が見えている範囲の外に出たら、見る場所を追いかけさせる
        右へ出たら赤い線が右寄り（9割の所）、左へ出たら左寄り（1割の所）に来るように動かす。
        端ぴったりにすると、次の1歩でまたすぐ外に出てしまうため"""
        span = self.zoom_end - self.zoom_start
        if self.position > self.zoom_end:
            self.scroll_to(self.position - span * 0.9)
        elif self.position < self.zoom_start:
            self.scroll_to(self.position - span * 0.1)

    def on_seek_ctrl_wheel(self, event):
        """Ctrl＋ホイール：マウスのある位置を中心に、拡大（奥へ回す）・縮小（手前へ回す）"""
        if not self.duration:
            return
        anchor = min(max((event.x - SEEK_PAD) / (self.seek_w - SEEK_PAD * 2), 0.0), 1.0)
        self.zoom_by(2.0 if event.delta > 0 else 0.5, self.x_to_time(event.x), anchor)

    def update_zoom_label(self):
        """拡大しているときだけ、見えている範囲（秒）を出す"""
        zoomed = self.zoom_end - self.zoom_start < self.duration - 1e-6
        self.zoom_label.config(text=f"表示 {self.zoom_start:.1f}〜{self.zoom_end:.1f}秒" if zoomed else "")
        # 横のスクロールバー：拡大しているときだけ出し、つまみの位置と長さを見えている範囲に合わせる（ステップ27）
        if zoomed:
            self.scrollbar.set(self.zoom_start / self.duration, self.zoom_end / self.duration)
            if not self.scrollbar.winfo_ismapped():
                self.scrollbar.pack(fill="x", padx=SEEK_PAD)
        else:
            self.scrollbar.pack_forget()

    def draw_seek(self):
        """シークバーを描き直す。灰色：動画全体、青：GIF に使う範囲、赤い線：いま見ている位置"""
        c = self.seek
        c.delete("all")
        middle = SEEK_H // 2
        c.create_rectangle(SEEK_PAD, middle - 4, self.seek_w - SEEK_PAD, middle + 4, fill=SUNKEN, outline="")
        if not self.duration:
            return
        start, end = self.read_time(self.start_var), self.read_time(self.end_var)  # 入力の途中などは None
        # 青い範囲：見えている範囲と重なるところだけ描く（time_to_x が端にそろえるので、はみ出さない）
        if start is not None and end is not None and end > start \
                and end >= self.zoom_start and start <= self.zoom_end:
            c.create_rectangle(self.time_to_x(start), middle - 4, self.time_to_x(end), middle + 4,
                               fill="#9fb6ea", outline="")
        # 始点（緑）・終点（オレンジ）の縦線（ステップ17）。ボタンの文字の色とそろえる
        # 見えている範囲の外にあるときは描かない（端に描くと、そこが始点だとまちがえるため。ステップ26）
        for seconds, color in ((start, START), (end, END)):
            if seconds is not None and self.in_view(seconds):
                sx = self.time_to_x(seconds)
                c.create_line(sx, 6, sx, SEEK_H - 6, fill=color, width=3)
        if self.in_view(self.position):
            # いまの位置：白いふちの青い丸（スマホ版と同じつまみ）
            x = self.time_to_x(self.position)
            c.create_oval(x - 10, middle - 10, x + 10, middle + 10, fill="#ffffff", outline="")
            c.create_oval(x - 7, middle - 7, x + 7, middle + 7, fill=ACCENT, outline="")

    def on_seek(self, event):
        """シークバーをクリック・ドラッグしたとき"""
        self.release_focus()
        if self.duration:
            self.set_position(self.x_to_time(event.x))

    def set_position(self, seconds):
        # フレームの区切りにそろえる（ステップ12）。動画の最後のフレームを超えないようにする
        seconds = min(max(gif_loop.snap_to_frame(seconds, self.frame_rate), 0.0), self.last_frame_time())
        self.position = seconds
        self.follow_position()  # 拡大中に赤い線が外へ出たら、見る場所を追いかけさせる（ステップ27）
        self.time_label.config(text=f"{self.timecode(seconds)} / {self.timecode(self.duration)}")
        self.draw_seek()
        self.request_frame(seconds)

    def request_frame(self, seconds):
        """その位置の絵をお願いする。取り出しは別のスレッドで行う
        ドラッグ中はお願いがたくさん来るので、取り出し中なら「最後のお願い」だけ覚えておき、終わったらそれを取り出す"""
        if self.frame_busy:
            self.frame_wanted = seconds
            return
        self.frame_busy = True
        self.frame_wanted = None
        path = self.video_path
        # 動画の最後ぴったりは絵が取れないことがあるので、ほんの少し手前にする
        seconds = min(seconds, max(0.0, self.duration - 0.05))
        view_w, view_h = self.view_w, self.view_h  # いまの絵の場所の大きさに合わせて取り出す（ステップ19）

        def work():
            try:
                # 画面を広げたら、小さい動画も大きく見せる（ステップ19）
                ppm = gif_loop.video_frame(path, seconds, view_w, view_h, upscale=True)
            except Exception:
                ppm = None
            self.root.after(0, self.on_frame, ppm)

        threading.Thread(target=work, daemon=True).start()

    def on_frame(self, ppm):
        """取り出せた絵を、真ん中に表示する"""
        self.frame_busy = False
        if ppm:
            self.view_image = tk.PhotoImage(data=ppm, format="PPM")
            self.view.delete("all")
            self.view.create_image(self.view_w // 2, self.view_h // 2, image=self.view_image, tags="frame")
            self.draw_crop()
            self.draw_drop_hint()
        if self.frame_wanted is not None:  # 取り出している間に、シークバーが動いていた
            self.request_frame(self.frame_wanted)

    # ---- 画面の大きさが変わったとき（ステップ19） ----

    def on_view_resize(self, event):
        """動画の絵の場所の大きさが変わったとき
        まず今の絵を真ん中に置き直し、枠も描き直す。新しい大きさの絵の取り出しは、広げ終わってから1回だけ行う
        （端を引っぱっている間は何十回も大きさが変わるので、そのたびに取り出すと重くなる）"""
        self.view_w, self.view_h = event.width, event.height
        self.view.coords("frame", self.view_w // 2, self.view_h // 2)
        self.draw_drop_hint()  # 点線の枠も、新しい大きさで描き直す（ステップ20）
        if self.view_image is not None and self.video_size[0]:
            self.draw_crop()  # 新しい絵が届くまでは、今の絵の大きさに合わせて枠を描く
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(150, self.after_resize)

    def after_resize(self):
        self.resize_job = None
        if self.video_path:
            self.request_frame(self.position)

    def on_seek_resize(self, event):
        """シークバーの長さが変わったら、描き直す"""
        self.seek_w = event.width
        self.draw_seek()

    # ---- 出力比率と切り抜き枠（ステップ9） ----

    def view_scale(self):
        """元の動画のピクセル → 画面のピクセル の倍率と、絵の左上の位置（絵は枠の真ん中に置いている）
        絵は、場所いっぱいまで（小さい動画は拡大して）見せる（ステップ19）"""
        vw, vh = self.video_size
        if self.view_image is not None:
            # 実際に見せている絵の大きさから倍率を出す（ステップ19）
            # 画面を広げた直後は、新しい大きさの絵が届くまで前の絵のままなので、それに枠を合わせる
            scale = self.view_image.width() / vw
        else:
            scale = min(self.view_w / vw, self.view_h / vh)
        return scale, (self.view_w - vw * scale) / 2, (self.view_h - vh * scale) / 2

    def on_ratio(self):
        """比率を選んだとき：その比率で入る、いちばん大きい枠を真ん中に置く"""
        ratio = RATIOS[self.ratio_var.get()]
        vw, vh = self.video_size
        if ratio is None or not vw:
            self.crop = None
        else:
            rw, rh = ratio
            w = min(vw, vh * rw / rh)
            h = w * rh / rw
            self.crop = [(vw - w) / 2, (vh - h) / 2, w, h]
        self.draw_crop()

    def draw_crop(self):
        """切り抜き枠を描く。枠の外は暗くして、どこが GIF になるか分かるようにする"""
        self.view.delete("crop")
        if not self.crop:
            self.crop_label.config(text="動画全体を使います" if self.video_path else "")
            return
        scale, ox, oy = self.view_scale()
        x, y, w, h = self.crop
        left, top = ox + x * scale, oy + y * scale
        right, bottom = left + w * scale, top + h * scale
        img_l, img_t = ox, oy
        img_r, img_b = ox + self.video_size[0] * scale, oy + self.video_size[1] * scale
        shade = dict(fill="black", stipple="gray50", outline="", tags="crop")  # 半分だけ黒で塗る＝暗く見える
        self.view.create_rectangle(img_l, img_t, img_r, top, **shade)
        self.view.create_rectangle(img_l, bottom, img_r, img_b, **shade)
        self.view.create_rectangle(img_l, top, left, bottom, **shade)
        self.view.create_rectangle(right, top, img_r, bottom, **shade)
        self.view.create_rectangle(left, top, right, bottom, outline="white", width=2, tags="crop")
        for cx, cy in self.corners():
            self.view.create_rectangle(cx - HANDLE, cy - HANDLE, cx + HANDLE, cy + HANDLE,
                                       fill="white", outline="#333333", tags="crop")
        # 説明が長いと左側の幅が広がって画面がずれるので、短くする（ステップ14）
        self.crop_label.config(text=f"{round(w)}×{round(h)}・枠は動かせます")
        self.view.tag_raise("hint")  # ドロップの案内は、枠より上に見せる（ステップ20）

    def corners(self):
        """枠の4つの角の、画面での位置（左上・右上・左下・右下）"""
        scale, ox, oy = self.view_scale()
        x, y, w, h = self.crop
        left, top = ox + x * scale, oy + y * scale
        right, bottom = left + w * scale, top + h * scale
        return [(left, top), (right, top), (left, bottom), (right, bottom)]

    def hit_test(self, ex, ey):
        """マウスの位置が、角（番号 0〜3）・枠の中（"move"）・外（None）のどれか"""
        if not self.crop:
            return None
        for i, (cx, cy) in enumerate(self.corners()):
            if abs(ex - cx) <= GRAB and abs(ey - cy) <= GRAB:
                return i
        (left, top), _, _, (right, bottom) = self.corners()
        if left <= ex <= right and top <= ey <= bottom:
            return "move"
        return None

    def on_view_hover(self, event):
        """マウスの形を変えて、つかめる場所だと分かるようにする"""
        hit = self.hit_test(event.x, event.y)
        cursor = {None: "", "move": "fleur", 0: "size_nw_se", 3: "size_nw_se", 1: "size_ne_sw", 2: "size_ne_sw"}[hit]
        self.view.config(cursor=cursor)

    def on_view_press(self, event):
        self.release_focus()
        hit = self.hit_test(event.x, event.y)
        if hit is None:
            self.drag = None
            return
        x, y, w, h = self.crop
        if hit == "move":
            self.drag = {"mode": "move", "mouse": (event.x, event.y), "start": (x, y)}
        else:
            # つかんだ角の、反対側の角を動かさない点（アンカー）にする
            anchor_x = x + w if hit in (0, 2) else x
            anchor_y = y + h if hit in (0, 1) else y
            self.drag = {"mode": "resize", "anchor": (anchor_x, anchor_y)}

    def on_view_drag(self, event):
        if not self.drag or not self.crop:
            return
        scale, ox, oy = self.view_scale()
        vw, vh = self.video_size
        x, y, w, h = self.crop
        if self.drag["mode"] == "move":
            # マウスが動いたぶんだけ枠を動かす。動画の外には出さない
            dx = (event.x - self.drag["mouse"][0]) / scale
            dy = (event.y - self.drag["mouse"][1]) / scale
            x = min(max(self.drag["start"][0] + dx, 0), vw - w)
            y = min(max(self.drag["start"][1] + dy, 0), vh - h)
        else:
            # アンカーからマウスまでの長さで大きさを決める。比率は選んだものに固定したまま
            ax, ay = self.drag["anchor"]
            mx = (event.x - ox) / scale  # マウスの位置を、元の動画のピクセルに直す
            my = (event.y - oy) / scale
            rw, rh = RATIOS[self.ratio_var.get()]
            to_right, to_bottom = mx >= ax, my >= ay
            room_w = (vw - ax) if to_right else ax   # その向きに広げられる、いちばん大きい横幅
            room_h = (vh - ay) if to_bottom else ay
            w = max(abs(mx - ax), abs(my - ay) * rw / rh)       # 大きく動かしたほうに合わせる
            w = min(w, room_w, room_h * rw / rh)                # 動画からはみ出さない
            w = max(w, MIN_CROP * max(1, rw / rh))              # 小さくなりすぎない
            h = w * rh / rw
            if w > room_w or h > room_h:  # 端に近すぎて、いちばん小さい大きさも入らないときは動かさない
                return
            x = ax if to_right else ax - w
            y = ay if to_bottom else ay - h
        self.crop = [x, y, w, h]
        self.draw_crop()

    # ---- シークバーの操作ボタン（ステップ13） ----

    def last_frame_time(self):
        """動画の最後のフレームの時刻（例：20秒・30fps なら、0 から数えて 599 枚目 = 19.967 秒）"""
        frames = math.ceil(self.duration * self.frame_rate - 1e-6)
        return max(0.0, (frames - 1) / self.frame_rate)

    def go_start(self):
        """始点の欄の位置へ飛ぶ"""
        start = self.read_time(self.start_var)
        if start is not None:
            self.set_position(start)

    def go_end(self):
        """終点の欄の位置へ飛ぶ（終点が動画の最後なら、最後のフレームへ）"""
        end = self.read_time(self.end_var)
        if end is not None:
            self.set_position(end)

    def step_frame(self, count):
        """count フレームだけ前（-1）や後ろ（+1）へ動く"""
        if self.duration:
            self.set_position(self.position + count / self.frame_rate)

    def on_arrow_key(self, event, direction, by_second):
        """←→キーが押されたとき（ステップ18）
        数字の欄に文字を打っている途中は、欄の中のカーソル移動に使うので、位置は動かさない"""
        if isinstance(event.widget, (tk.Entry, tk.Spinbox)):
            return
        if by_second:
            self.step_seconds(direction * 1.0)
        else:
            self.step_frame(direction)

    def release_focus(self):
        """シークバーや動画をクリックしたら、数字の欄からキーボードの入力先を外す
        （欄を直したあとでも、すぐ ←→ キーで位置を動かせるようにする）"""
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Spinbox)):
            self.root.focus_set()

    def step_seconds(self, seconds):
        """seconds 秒だけ前（マイナス）や後ろ（プラス）へ動く（ステップ17）。着いた先はフレームの区切りにそろう"""
        if self.duration:
            self.set_position(self.position + seconds)

    def set_start_here(self):
        """今の位置を始点にする。終点より後ろなら、範囲の長さを保ったまま終点もついてくる（ステップ29）"""
        pos = self.position
        start, end = self.read_time(self.start_var), self.read_time(self.end_var)
        if start is not None and end is not None and start < end <= pos:
            new_end = min(gif_loop.snap_to_frame(pos + (end - start), self.frame_rate), self.duration)
            if new_end <= pos:
                self.status_label.config(text="動画の最後の絵は始点にできません。少し前に戻してください")
                return
            self.end_var.set(self.timecode(new_end))  # 先に終点を動かして、一瞬でも逆の範囲にならないようにする
            self.start_var.set(self.timecode(pos))
            self.status_label.config(text="始点を決めました（終点もいっしょに動かしました）")
            return
        self.start_var.set(self.timecode(pos))
        self.status_label.config(text="始点を決めました")

    def set_end_here(self):
        """今の位置を終点にする。始点より前なら、範囲の長さを保ったまま始点もついてくる（ステップ29）"""
        pos = self.position
        start, end = self.read_time(self.start_var), self.read_time(self.end_var)
        if start is not None and end is not None and pos <= start < end:
            new_start = max(gif_loop.snap_to_frame(pos - (end - start), self.frame_rate), 0.0)
            if new_start >= pos:
                self.status_label.config(text="動画の最初の絵は終点にできません。少し先へ進めてください")
                return
            self.start_var.set(self.timecode(new_start))  # 先に始点を動かして、一瞬でも逆の範囲にならないようにする
            self.end_var.set(self.timecode(pos))
            self.status_label.config(text="終点を決めました（始点もいっしょに動かしました）")
            return
        self.end_var.set(self.timecode(pos))
        self.status_label.config(text="終点を決めました")

    def add_speed_slider(self, parent):
        """再生スピードの細かいスライダー（ステップ31）。欄と結びつけ、どちらを動かしても、もう一方が合わせて動く
        スライダーは 0.25〜4倍・0.05倍きざみ（スマホ版と同じ）。それより外の数字は、欄に打てば使える"""
        self.speed_syncing = False  # 欄 → スライダー → 欄… と、合わせ合いが続かないようにする目印
        self.speed_scale = ttk.Scale(parent, from_=0.25, to=4.0, orient="horizontal", length=240,
                                     style="Speed.Horizontal.TScale", command=self.on_speed_scale)
        self.speed_scale.set(float(self.speed_var.get()))
        self.speed_scale.pack(side="left")
        self.speed_var.trace_add("write", lambda *_: self.on_speed_text())

    def on_speed_scale(self, value):
        """スライダーを動かしたとき：欄の数字を合わせる（0.05倍きざみにそろえる）"""
        if self.speed_syncing:
            return
        value = round(float(value) / 0.05) * 0.05
        # Tk のスライダーは、位置を合わせたあと少し遅れてここを呼ぶことがある。
        # 欄の数字がすでにこの位置に当たるなら書きかえない（打っている途中の「1.」などを消さないため）
        try:
            typed = float(self.speed_var.get().strip().translate(ZENKAKU_TO_HANKAKU))
            if abs(round(min(max(typed, 0.25), 4.0) / 0.05) * 0.05 - float(value)) < 1e-6:
                return
        except ValueError:
            pass
        self.speed_syncing = True
        self.speed_var.set(f"{float(value):.2f}")
        self.speed_syncing = False

    def on_speed_text(self):
        """欄の数字が変わったとき：スライダーの位置を合わせる（数字にできないとき・範囲の外のときは動かさない）"""
        if self.speed_syncing:
            return
        try:
            value = float(self.speed_var.get().strip().translate(ZENKAKU_TO_HANKAKU))
        except ValueError:
            return
        self.speed_syncing = True
        self.speed_scale.set(min(max(value, 0.25), 4.0))
        self.speed_syncing = False

    def update_length(self):
        """範囲の長さと、できる GIF の長さ（往復・片道）を、タイムの下に出す（ステップ30）
        往復は、折り返しの絵を2回使わないぶん（2枚）短くなる。スマホ版と同じ計算"""
        settings, problems = self.read_settings()
        start, end = settings.get("start"), settings.get("end")
        if problems or start is None or end is None or end <= start or settings["fps"] <= 0 or settings["speed"] <= 0:
            self.length_label.config(text="範囲 —｜GIF 往復 —・片道 —")
            return
        fps, speed = settings["fps"], settings["speed"]
        n = max(1, round((end - start) / speed * fps))  # 片道で使う絵の枚数
        both = n * 2 - 2 if n > 2 else n
        self.length_label.config(text=f"範囲 {end - start:.2f}秒｜GIF 往復 {both / fps:.1f}秒・片道 {n / fps:.1f}秒")

    def on_range_changed(self):
        """始点・終点の欄が変わったとき：シークバーを描き直し、逆になっていれば画面の下で知らせる"""
        self.draw_seek()
        self.update_length()
        if not self.video_path or self.converting:
            return
        start, end = self.read_time(self.start_var), self.read_time(self.end_var)
        if start is None or end is None:
            return
        reversed_text = "始点が終点より後ろになっています"
        if start >= end:
            self.status_label.config(text=reversed_text)
        elif self.status_label["text"] == reversed_text:  # 直ったら、案内をもとに戻す
            self.status_label.config(text="項目を決めて「往復 GIF を保存」を押してください")

    # ---- タイムの表示と読み取り（ステップ12） ----

    def timecode(self, seconds):
        """秒 → 「時:分:秒:フレーム」"""
        return gif_loop.seconds_to_timecode(seconds, self.frame_rate)

    def read_time(self, var):
        """タイムの欄を秒にする。読めないときは None"""
        try:
            return gif_loop.timecode_to_seconds(var.get().translate(ZENKAKU_TO_HANKAKU), self.frame_rate)
        except ValueError:
            return None

    def read_settings(self):
        """入力欄の文字を数字にする。数字にできない欄があれば、どの欄かを書いた理由のリストも返す（ステップ4）"""
        fields = [  # （名前, 画面での呼び方, 入れ物, 数字の種類）
            ("start", "開始", self.start_var, "time"),
            ("end", "終了", self.end_var, "time"),
            ("width", "横幅", self.width_var, int),
            ("fps", "fps", self.fps_var, int),
            ("speed", "再生スピード", self.speed_var, float),
        ]
        settings, problems = {}, []
        for key, label, var, kind in fields:
            text = var.get().strip().translate(ZENKAKU_TO_HANKAKU)  # 全角で打った数字も受け付ける
            try:
                if kind == "time":  # 時:分:秒:フレーム か 秒（ステップ12）
                    settings[key] = gif_loop.timecode_to_seconds(text, self.frame_rate)
                else:
                    settings[key] = kind(text)
            except ValueError as error:
                if kind == "time":
                    problems.append(f"{label}：{error}")
                else:
                    example = "整数（例：480）" if kind is int else "数字（例：1.5）"
                    problems.append(f"{label}に {example} を入れてください")
        return settings, problems

    def make_gif(self):
        """「GIF出力」：保存する。プレビューと設定が同じなら、作り直さずにプレビューの GIF を保存する（ステップ24）"""
        settings = self.checked_settings()
        if settings is None:
            return
        key = self.settings_key(settings)
        last = self.last_preview
        if last and last["key"] == key and last["result"]["path"].exists():
            self.save_preview_copy(last["result"])
            return
        if not self.confirm_frames(settings):
            return
        self.start_convert(gif_loop.default_output_path(self.video_path), settings, "save", key)

    def make_once_gif(self):
        """［1回だけ出力］：逆再生をつながず、順再生を1回だけ再生して止まる GIF を保存する（ステップ25）"""
        settings = self.checked_settings()
        if settings is None:
            return
        settings["once"] = True
        if not self.confirm_frames(settings):
            return
        self.start_convert(gif_loop.default_output_path(self.video_path, "once"), settings, "once", None)

    def preview_gif(self):
        """［プレビュー］：一時フォルダに GIF を作って再生するだけ。動画の横には保存しない（ステップ24）"""
        settings = self.checked_settings()
        if settings is None or not self.confirm_frames(settings):
            return
        if self.temp_dir is None:
            # このツール専用の一時フォルダを作る。閉じるときに、このフォルダごと消す
            self.temp_dir = Path(tempfile.mkdtemp(prefix="gif-loop-tool_"))
        self.preview_count += 1
        output = self.temp_dir / f"preview_{self.preview_count}.gif"
        self.start_convert(output, settings, "preview", self.settings_key(settings))

    def settings_key(self, settings):
        """「プレビューのときと設定が同じか」をくらべるための目印（動画と、すべての設定をまとめた文字）"""
        return repr((str(self.video_path), sorted(settings.items())))

    def save_preview_copy(self, result):
        """プレビューの GIF を、動画の横に保存する（作り直さないので、すぐ終わる）"""
        output = gif_loop.default_output_path(self.video_path)
        try:
            # "xb"：同じ名前のファイルがあったら書かずに失敗する。うっかり上書きしないための書き方
            with open(result["path"], "rb") as src, open(output, "xb") as dst:
                shutil.copyfileobj(src, dst)
        except OSError as error:
            messagebox.showerror("保存できませんでした", str(error))
            return
        self.status_label.config(text=f"保存しました：{output.name}（プレビューと同じ）")

    def checked_settings(self):
        """入力欄を読み、おかしなところがあれば知らせる。問題なければ設定の辞書を返す（ステップ24で make_gif から分けた）"""
        settings, problems = self.read_settings()
        if not problems:
            problems = gif_loop.check_settings(duration=self.duration, **settings)
        # サイズ上限（ステップ10）
        settings["preset"] = self.preset_var.get()
        settings["custom_mb"] = None
        if gif_loop.SIZE_PRESETS[settings["preset"]][0] == "custom":
            try:
                settings["custom_mb"] = float(self.custom_mb_var.get().strip().translate(ZENKAKU_TO_HANKAKU))
                if settings["custom_mb"] <= 0:
                    raise ValueError
            except ValueError:
                problems.append("指定サイズに 0 より大きい数字（例：8）を入れてください")
        if problems:
            messagebox.showerror("入力を確かめてください", "\n".join(problems))
            return None
        settings["crop"] = tuple(self.crop) if self.crop else None  # 切り抜き枠（ステップ9）
        return settings

    def confirm_frames(self, settings):
        """枚数が多くて重くなりそうなら、続けるかを聞く。続けてよければ True"""
        # X の「350枚まで」などの決まりで fps が下がるなら、それを入れて枚数を見積もる
        _, max_frames, max_w, max_h = gif_loop.SIZE_PRESETS[settings["preset"]]
        info = {"duration": self.duration, "width": self.video_size[0], "height": self.video_size[1]}
        try:
            _, fps, _ = gif_loop.apply_platform_rules(settings["start"], settings["end"], settings["width"],
                                                      settings["fps"], settings["speed"], settings["crop"],
                                                      info, max_frames, max_w, max_h, settings.get("once", False))
        except gif_loop.FileProblem as error:
            messagebox.showerror("入力を確かめてください", str(error))
            return False
        # 終了が動画より長いときは、動画の最後までにして枚数を見積もる
        end = min(settings["end"], self.duration) if self.duration else settings["end"]
        frames = gif_loop.estimate_frames(settings["start"], end, fps, settings["speed"], settings.get("once", False))
        return frames <= gif_loop.HEAVY_FRAMES or self.confirm_heavy(frames)

    def start_convert(self, output, settings, mode, key):
        """変換を別のスレッドで始める。mode は "preview"（一時フォルダ）か "save"（動画の横に保存）"""
        self.make_button.config(state="disabled")
        self.preview_button.config(state="disabled")
        self.once_button.config(state="disabled")
        self.converting = True
        self.progress_base = "プレビューを作っています" if mode == "preview" else "GIF を保存しています"
        self.status_label.config(text=self.progress_base + "…")
        self.result_label.config(text="")
        # 進み具合のバーと［やめる］を出す（ステップ32）
        self.cancel_event = threading.Event()
        self.attempt, self.attempt_started = 0, time.time()
        self.progress_bar["value"] = 0
        self.cancel_button.config(state="normal", text="やめる")
        self.cancel_button.pack(side="right")
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        threading.Thread(target=self.convert, args=(output, settings, mode, key), daemon=True).start()

    def cancel_convert(self):
        """［やめる］：作っている ffmpeg を止める合図を出す（ステップ32）。止まったら on_done が呼ばれる"""
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.cancel_button.config(state="disabled", text="やめています…")

    def on_progress(self, attempt, fraction):
        """進み具合（0〜1）が届いたとき：バーを動かし、「あと約○秒」を出す（ステップ32）
        サイズ上限に収めるため作り直すときは、回ごとに 0 から数え直す"""
        if not self.converting:
            return
        now = time.time()
        if attempt != self.attempt:
            self.attempt, self.attempt_started = attempt, now
        self.progress_bar["value"] = fraction * 100
        text = f"{self.progress_base}　{fraction * 100:.0f}%"
        elapsed = now - self.attempt_started
        if fraction >= 0.05 and elapsed >= 0.5:  # 始まったばかりは計算がぶれるので、少し進んでから出す
            text += f"・あと約 {max(1, round(elapsed * (1 - fraction) / fraction))} 秒"
        self.status_label.config(text=text)

    def on_preset(self):
        """「指定サイズ」を選んだときだけ、MB の欄に入力できるようにする"""
        custom = gif_loop.SIZE_PRESETS[self.preset_var.get()][0] == "custom"
        self.custom_mb_entry.config(state="normal" if custom else "disabled")

    def confirm_heavy(self, frames):
        """枚数が多くて重くなりそうなときに、続けるかを聞く"""
        return messagebox.askyesno(
            "重くなりそうです",
            f"できる GIF は約 {frames} 枚になり、作るのに時間がかかり、ファイルも大きくなりそうです。\n"
            "範囲を短くする、fps を下げる、横幅を小さくすると軽くなります。\n\nこのまま作りますか？")

    def convert(self, output, settings, mode, key):
        """別のスレッドで変換する。終わったら、画面の書きかえは root.after で元のスレッドにお願いする
        （tkinter の画面は、作ったスレッドからしか安全にさわれないため）"""
        # 作り直しの途中のようす（何回目か）は、進み具合の文の頭に使う（ステップ32）
        def progress(text):
            if "回目" in text:  # 「GIF を作っています…（2 回目：横幅 212・20fps）」→ …を取って使う
                self.progress_base = text.replace("…", "")
        report = lambda attempt, fraction: self.root.after(0, self.on_progress, attempt, fraction)
        try:
            result = gif_loop.make_gif_within(self.video_path, output, progress=progress, report=report,
                                              cancel=self.cancel_event, **settings)
            self.root.after(0, self.on_done, result, None, mode, key)
        except gif_loop.Cancelled:  # ［やめる］で止めた（ステップ32）
            self.root.after(0, self.on_done, None, "cancelled", mode, key)
        except (gif_loop.FfmpegMissing, gif_loop.FileProblem) as error:
            self.root.after(0, self.on_done, None, error, mode, key)
        except Exception as error:  # 思わぬ失敗でも、ボタンが押せないまま止まらないようにする
            self.root.after(0, self.on_done, None, f"思わぬエラーが起きました：{error}", mode, key)

    def on_done(self, result, error, mode="save", key=None):
        self.converting = False
        self.make_button.config(state="normal")
        self.preview_button.config(state="normal")
        self.once_button.config(state="normal")
        self.progress_bar.pack_forget()  # 進み具合のバーと［やめる］をしまう（ステップ32）
        self.cancel_button.pack_forget()
        if error == "cancelled":
            self.status_label.config(text="やめました（GIF は保存していません）")
            return
        if error:
            self.status_label.config(text="作れませんでした")
            messagebox.showerror("作れませんでした", str(error))
            return
        saved, fps = result["path"], result["fps"]  # fps は自動で下げたかもしれないので、実際に使ったものを使う
        if mode == "preview":
            # 前のプレビューの GIF は、もう使わないので消す（このツールの一時フォルダの中のものだけ）
            if self.last_preview and self.last_preview["result"]["path"] != saved:
                self.last_preview["result"]["path"].unlink(missing_ok=True)
            self.last_preview = {"key": key, "result": result}
            done_text = "プレビュー中（まだ保存していません）"
        elif mode == "once":
            done_text = f"保存しました：{saved.name}（往復しない GIF・右の絵をクリックでもう一度）"
        else:
            done_text = f"保存しました：{saved.name}"
        self.status_label.config(text=done_text)
        lines = [f"大きさ：{result['size'] / gif_loop.BYTES_PER_MB:.2f}MB（横幅 {result['width']}・{fps}fps）"]
        lines += [f"・{note}" for note in result["notes"]]
        self.result_label.config(text="\n".join(lines))
        try:
            self.show_preview(saved, fps, once=(mode == "once"))
        except Exception as error:  # 再生できなくても、GIF そのものはできている
            self.status_label.config(text=f"{done_text}（画面での再生はできませんでした）")
            messagebox.showwarning("再生できませんでした", f"GIF はできましたが、画面で再生できませんでした：{error}")

    def on_close(self):
        """ツールを閉じるとき：プレビュー用に作った一時フォルダを、中身ごと消す（ステップ24）
        消すのは、このツールが tempfile.mkdtemp で作ったフォルダだけ"""
        self.stop_preview()
        if self.cancel_event is not None:  # 作っている途中なら、ffmpeg も止める（ステップ32）
            self.cancel_event.set()
        if self.temp_dir is not None:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.root.destroy()

    def show_preview(self, gif_path, fps, once=False):
        """できた GIF を画面の中でくり返し再生する（ステップ3）
        once=True なら、作った GIF と同じく1回だけ再生して最後の絵で止める（ステップ25）
        tkinter の PhotoImage は GIF の1枚目しか動かさないので、「-index 番号」で1枚ずつ取り出し、
        決まった時間ごとに絵を入れかえてアニメーションにする"""
        self.stop_preview()
        # GIF は容量を減らすため、2枚目からは「前の絵から変わった部分だけ」が入っている
        # 完成した絵にする作業と、はみ出さないように縮める作業は、ffmpeg にまとめてまかせる
        # （tkinter で1枚ずつ取り出すと、毎回 GIF を最初から読み直すので、とても遅かった）
        frames = [tk.PhotoImage(data=ppm, format="PPM")
                  for ppm in gif_loop.preview_frames(gif_path, GIF_VIEW_W, GIF_VIEW_H)]
        if not frames:
            return
        self.preview_frames = frames
        self.preview_index = 0
        self.preview_delay = max(20, round(1000 / fps))
        self.preview_once = once
        # 1回だけの GIF は、絵をクリックすると最初から再生し直す
        self.preview_label.config(cursor="hand2" if once else "")
        self.next_preview_frame()

    def replay_preview(self, event=None):
        """出力プレビューの絵をクリックしたとき：1回だけの GIF なら、最初からもう一度再生する（ステップ25）"""
        if self.preview_once and self.preview_frames and self.preview_job is None:
            self.preview_index = 0
            self.next_preview_frame()

    def next_preview_frame(self):
        self.preview_label.config(image=self.preview_frames[self.preview_index])
        if self.preview_once and self.preview_index == len(self.preview_frames) - 1:
            self.preview_job = None  # 最後の絵で止める
            return
        self.preview_index = (self.preview_index + 1) % len(self.preview_frames)  # 最後まで来たら最初に戻る
        self.preview_job = self.root.after(self.preview_delay, self.next_preview_frame)

    def stop_preview(self):
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None
        self.preview_label.config(image="", text="")
        self.preview_frames = []


def set_icon(root):
    """画面の左上とタスクバーに、ツールのアイコンを付ける（ステップ21）
    exe の中から動くときは、アイコンのファイルは一時的に広げた場所（sys._MEIPASS）にある"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    icon = base / "icon.ico"
    if not icon.exists():
        return  # アイコンが無くても、ツールは使える
    try:
        # Python から起動したとき、タスクバーに Python のアイコンではなく、このツールのアイコンを出すための名札
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("GifLoopTool")
    except (AttributeError, OSError):
        pass
    root.iconbitmap(default=str(icon))  # default にすると、確認の小さな画面にも同じアイコンが付く


def main():
    root = TkinterDnD.Tk()  # ドラッグ＆ドロップを受け取れる画面
    set_icon(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
