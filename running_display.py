"""Running 8-week summary display for MagTag e-ink."""
import time
import displayio
import terminalio
from adafruit_display_text import label


def show(magtag, url, refresh_delay):
    """Fetch 8-week running summary and display as a table."""
    if not url:
        print("No running API URL configured")
        return

    # Fetch data with retries
    data = None
    for _attempt in range(3):
        print("Fetching running data (attempt {})...".format(_attempt + 1))
        try:
            resp = magtag.network.fetch(url)
            data = resp.json()
            break
        except Exception as error:
            print("Fetch attempt {} failed: {}".format(_attempt + 1, error))
            if _attempt < 2:
                time.sleep(3)

    if data is None:
        print("All fetch attempts failed")
        err_group = displayio.Group()
        bg_bmp = displayio.Bitmap(296, 128, 1)
        bg_pal = displayio.Palette(1)
        bg_pal[0] = 0xFFFFFF
        err_group.append(displayio.TileGrid(bg_bmp, pixel_shader=bg_pal))
        err_lbl = label.Label(terminalio.FONT, text="Running: Error", color=0x000000)
        err_lbl.anchor_point = (0.5, 0.5)
        err_lbl.anchored_position = (148, 64)
        err_group.append(err_lbl)
        magtag.display.root_group = err_group
        time.sleep(magtag.display.time_to_refresh + refresh_delay)
        magtag.display.refresh()
        time.sleep(magtag.display.time_to_refresh + refresh_delay)
        return

    weeks = data.get("weeks", [])
    del data
    del resp
    import gc
    gc.collect()

    if not weeks:
        print("No running weeks data")
        return

    # --- Build display group ---
    group = displayio.Group()

    # White background
    bg_bmp = displayio.Bitmap(296, 128, 1)
    bg_pal = displayio.Palette(1)
    bg_pal[0] = 0xFFFFFF
    group.append(displayio.TileGrid(bg_bmp, pixel_shader=bg_pal))

    # Title
    title = label.Label(terminalio.FONT, text="RUNNING - LAST 8 WEEKS", color=0x000000)
    title.anchor_point = (0.5, 0)
    title.anchored_position = (148, 2)
    group.append(title)

    # Column header
    hdr = label.Label(
        terminalio.FONT,
        text="WEEK    MILES  PACE   HR  RUNS",
        color=0x000000
    )
    hdr.anchor_point = (0, 0)
    hdr.anchored_position = (4, 16)
    group.append(hdr)

    # Data rows — 8 weeks, each 12px tall starting at y=28
    for i, w in enumerate(weeks):
        wk = w.get("wk", "--/--")
        miles = w.get("miles", 0)
        pace = w.get("pace", "--")
        hr = w.get("hr")
        runs = w.get("runs", 0)

        hr_str = str(hr) if hr else "--"

        line = "{:<7s} {:5.1f}  {:<5s} {:>3s}  {:>2d}".format(
            wk, miles, pace, hr_str, runs
        )

        row = label.Label(terminalio.FONT, text=line, color=0x000000)
        row.anchor_point = (0, 0)
        row.anchored_position = (4, 28 + i * 12)
        group.append(row)

    # --- Refresh display ---
    magtag.display.root_group = group
    time.sleep(magtag.display.time_to_refresh + refresh_delay)
    magtag.display.refresh()
    time.sleep(magtag.display.time_to_refresh + refresh_delay)
