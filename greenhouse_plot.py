"""Greenhouse 24h history plot for MagTag e-ink display."""
import time
import displayio
import bitmaptools
import terminalio
from adafruit_display_text import label


def show(magtag, url, refresh_delay):
    """Fetch 24h greenhouse history and display a temperature/humidity plot."""
    if not url:
        print("No greenhouse history URL configured")
        return

    # Fetch history data with retries (sockets may not be ready after deep sleep)
    data = None
    for _fetch_attempt in range(3):
        print("Fetching greenhouse history (attempt {})...".format(_fetch_attempt + 1))
        try:
            resp = magtag.network.fetch(url)
            data = resp.json()
            break
        except Exception as error:
            print("Fetch attempt {} failed: {}".format(_fetch_attempt + 1, error))
            if _fetch_attempt < 2:
                time.sleep(3)
    if data is None:
        print("All fetch attempts failed")
        err_group = displayio.Group()
        err_lbl = label.Label(terminalio.FONT, text="GH History: Error", color=0x000000)
        err_lbl.anchor_point = (0.5, 0.5)
        err_lbl.anchored_position = (148, 64)
        err_group.append(err_lbl)
        magtag.display.root_group = err_group
        time.sleep(magtag.display.time_to_refresh + refresh_delay)
        magtag.display.refresh()
        time.sleep(magtag.display.time_to_refresh + refresh_delay)
        return

    temp_data = data["t"]
    humid_data = data["h"]
    ago_data = data.get("ago")
    stats = data["stats"]

    # Free response memory
    del data
    del resp
    import gc
    gc.collect()

    n = len(temp_data)
    if n < 1:
        print("Insufficient greenhouse data for plot")
        return

    # --- Plot layout constants ---
    # Display is 296 x 128
    PLOT_X = 22       # left edge of plot (room for Y-axis labels)
    PLOT_Y = 16       # top edge of plot (room for title/stats row)
    PLOT_W = 215      # plot bitmap width (narrower to fit current values on right)
    PLOT_H = 90       # plot bitmap height

    # --- Determine Y-axis ranges ---
    # Temperature: auto-scale with padding
    t_lo = int(stats["t_min"]) - 3
    t_hi = int(stats["t_max"]) + 3
    if t_hi - t_lo < 10:
        mid = (t_hi + t_lo) // 2
        t_lo = mid - 5
        t_hi = mid + 5

    # Humidity: always 0-100%
    h_lo = 0
    h_hi = 100

    # --- Create plot bitmap (4-color grayscale) ---
    plot_bmp = displayio.Bitmap(PLOT_W, PLOT_H, 4)
    plot_pal = displayio.Palette(4)
    plot_pal[0] = 0xFFFFFF  # white (background)
    plot_pal[1] = 0xAAAAAA  # light gray (grid lines)
    plot_pal[2] = 0x555555  # dark gray (humidity trace)
    plot_pal[3] = 0x000000  # black (temperature trace + axes)

    plot_bmp.fill(0)  # white background

    # --- Draw dashed grid lines (light gray) ---
    for frac_q in range(1, 4):  # 25%, 50%, 75%
        gy = PLOT_H - 1 - (frac_q * (PLOT_H - 1)) // 4
        for x in range(0, PLOT_W, 4):
            if x + 1 < PLOT_W:
                plot_bmp[x, gy] = 1
                plot_bmp[x + 1, gy] = 1

    # --- Draw axes (black) ---
    bitmaptools.draw_line(plot_bmp, 0, 0, 0, PLOT_H - 1, 3)           # Y-axis
    bitmaptools.draw_line(plot_bmp, 0, PLOT_H - 1, PLOT_W - 1, PLOT_H - 1, 3)  # X-axis

    # --- Helper to draw a 3x3 dot at (cx, cy) ---
    def draw_dot(cx, cy, color):
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                px = cx + dx
                py = cy + dy
                if 0 <= px < PLOT_W and 0 <= py < PLOT_H:
                    plot_bmp[px, py] = color

    # --- Map hours-ago to x pixel (24h ago = left, now = right) ---
    def ago_to_x(hours_ago):
        return int((1.0 - hours_ago / 24.0) * (PLOT_W - 1))

    # Pre-compute x positions from ago data (or fall back to even spacing)
    x_pos = []
    for i in range(n):
        if ago_data:
            x_pos.append(max(0, min(PLOT_W - 1, ago_to_x(ago_data[i]))))
        elif n > 1:
            x_pos.append((i * (PLOT_W - 1)) // (n - 1))
        else:
            x_pos.append(PLOT_W - 1)

    # --- Plot temperature trace (black) with dots ---
    for i in range(n):
        py = PLOT_H - 1 - int((temp_data[i] - t_lo) / (t_hi - t_lo) * (PLOT_H - 1))
        py = max(0, min(PLOT_H - 1, py))
        if i < n - 1:
            y2 = PLOT_H - 1 - int((temp_data[i + 1] - t_lo) / (t_hi - t_lo) * (PLOT_H - 1))
            y2 = max(0, min(PLOT_H - 1, y2))
            bitmaptools.draw_line(plot_bmp, x_pos[i], py, x_pos[i + 1], y2, 3)
        draw_dot(x_pos[i], py, 3)

    # --- Plot humidity trace (dark gray) with dots ---
    for i in range(n):
        py = PLOT_H - 1 - int((humid_data[i] - h_lo) / (h_hi - h_lo) * (PLOT_H - 1))
        py = max(0, min(PLOT_H - 1, py))
        if i < n - 1:
            y2 = PLOT_H - 1 - int((humid_data[i + 1] - h_lo) / (h_hi - h_lo) * (PLOT_H - 1))
            y2 = max(0, min(PLOT_H - 1, y2))
            bitmaptools.draw_line(plot_bmp, x_pos[i], py, x_pos[i + 1], y2, 2)
        draw_dot(x_pos[i], py, 2)

    # --- Build display group ---
    plot_group = displayio.Group()

    # White background covering full 296x128 display
    bg_bmp = displayio.Bitmap(296, 128, 1)
    bg_pal = displayio.Palette(1)
    bg_pal[0] = 0xFFFFFF
    plot_group.append(displayio.TileGrid(bg_bmp, pixel_shader=bg_pal))

    # Title
    title_lbl = label.Label(terminalio.FONT, text="GREENHOUSE 24H", color=0x000000)
    title_lbl.anchor_point = (0, 0)
    title_lbl.anchored_position = (2, 2)
    plot_group.append(title_lbl)

    # Temperature stats: min/max/avg
    t_stats_lbl = label.Label(
        terminalio.FONT,
        text="T:{:.0f}/{:.0f}/{:.0f}F".format(stats['t_min'], stats['t_max'], stats['t_avg']),
        color=0x000000
    )
    t_stats_lbl.anchor_point = (0, 0)
    t_stats_lbl.anchored_position = (110, 2)
    plot_group.append(t_stats_lbl)

    # Humidity stats: min/max/avg
    h_stats_lbl = label.Label(
        terminalio.FONT,
        text="H:{:.0f}/{:.0f}/{:.0f}%".format(stats['h_min'], stats['h_max'], stats['h_avg']),
        color=0x555555
    )
    h_stats_lbl.anchor_point = (0, 0)
    h_stats_lbl.anchored_position = (210, 2)
    plot_group.append(h_stats_lbl)

    # Plot bitmap TileGrid
    plot_tg = displayio.TileGrid(plot_bmp, pixel_shader=plot_pal, x=PLOT_X, y=PLOT_Y)
    plot_group.append(plot_tg)

    # Y-axis labels (left side = temperature)
    yt_lbl = label.Label(terminalio.FONT, text=str(t_hi), color=0x000000)
    yt_lbl.anchor_point = (1, 0)
    yt_lbl.anchored_position = (PLOT_X - 2, PLOT_Y)
    plot_group.append(yt_lbl)

    yb_lbl = label.Label(terminalio.FONT, text=str(t_lo), color=0x000000)
    yb_lbl.anchor_point = (1, 1)
    yb_lbl.anchored_position = (PLOT_X - 2, PLOT_Y + PLOT_H)
    plot_group.append(yb_lbl)

    # Y-axis labels (right side = humidity) - far right
    hr_lbl = label.Label(terminalio.FONT, text="100%", color=0x555555)
    hr_lbl.anchor_point = (1, 0)
    hr_lbl.anchored_position = (294, PLOT_Y)
    plot_group.append(hr_lbl)

    hb_lbl = label.Label(terminalio.FONT, text="0%", color=0x555555)
    hb_lbl.anchor_point = (1, 1)
    hb_lbl.anchored_position = (294, PLOT_Y + PLOT_H)
    plot_group.append(hb_lbl)

    # X-axis time labels (actual clock hours)
    now_hour = time.localtime().tm_hour
    for i in range(5):
        hours_ago = 24 - i * 6  # 24, 18, 12, 6, 0
        if hours_ago == 0:
            txt = "now"
        else:
            h = (now_hour - hours_ago) % 24
            suffix = "a" if h < 12 else "p"
            h12 = h % 12
            if h12 == 0:
                h12 = 12
            txt = "{}{}".format(h12, suffix)
        xl = label.Label(terminalio.FONT, text=txt, color=0x000000)
        xl.anchor_point = (0.5, 0)
        xl.anchored_position = (PLOT_X + (i * (PLOT_W - 1)) // 4, PLOT_Y + PLOT_H + 2)
        plot_group.append(xl)

    # Current temp/humidity values - next to last data point
    cur_temp = temp_data[-1]
    cur_humid = humid_data[-1]
    label_x = PLOT_X + PLOT_W + 2  # just right of plot area

    cur_t_py = PLOT_Y + PLOT_H - 1 - int((cur_temp - t_lo) / (t_hi - t_lo) * (PLOT_H - 1))
    cur_t_py = max(PLOT_Y, min(PLOT_Y + PLOT_H - 1, cur_t_py))
    cur_h_py = PLOT_Y + PLOT_H - 1 - int((cur_humid - h_lo) / (h_hi - h_lo) * (PLOT_H - 1))
    cur_h_py = max(PLOT_Y, min(PLOT_Y + PLOT_H - 1, cur_h_py))

    # If labels would overlap (within 10px), spread them apart
    if abs(cur_t_py - cur_h_py) < 10:
        mid = (cur_t_py + cur_h_py) // 2
        cur_t_py = mid - 6
        cur_h_py = mid + 6

    ct_lbl = label.Label(terminalio.FONT, text="{:.0f}F".format(cur_temp), color=0x000000)
    ct_lbl.anchor_point = (0, 0.5)
    ct_lbl.anchored_position = (label_x, cur_t_py)
    plot_group.append(ct_lbl)

    ch_lbl = label.Label(terminalio.FONT, text="{:.0f}%".format(cur_humid), color=0x555555)
    ch_lbl.anchor_point = (0, 0.5)
    ch_lbl.anchored_position = (label_x, cur_h_py)
    plot_group.append(ch_lbl)

    # --- Refresh display ---
    magtag.display.root_group = plot_group
    time.sleep(magtag.display.time_to_refresh + refresh_delay)
    magtag.display.refresh()
    time.sleep(magtag.display.time_to_refresh + refresh_delay)
