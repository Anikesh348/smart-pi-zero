# Pi Zero TV Launcher

A lightweight Flask TV launcher with a mobile remote. It uses plain HTML, CSS, and vanilla JavaScript. The app is intentionally small; the browser is configurable so a Pi Zero 2W can use a lighter host browser such as `surf` or `cog` instead of defaulting to Chromium.

Use this only on a trusted LAN or Tailscale network.

## Features

- Dark TV launcher at `/tv`
- Mobile remote at `/remote`
- Shortcuts for YouTube, Moviehub, and a simple browser page
- Safe allowlisted commands only
- Remote navigation: arrows, OK, tab, back, forward, page up/down, click, mouse nudges
- Remote typing through `xdotool`
- Volume up/down/mute and reboot commands
- Docker support with a tiny default image
- Dry-run mode for Mac/headless testing

## Shortcuts

Configured in `config.json`:

```json
{
  "apps": [
    {
      "id": "youtube",
      "label": "YouTube",
      "url": "https://www.youtube.com/tv",
      "theme": "red"
    },
    {
      "id": "moviehub",
      "label": "Moviehub",
      "url": "https://openmovies.hostingfrompurva.xyz",
      "theme": "violet"
    },
    {
      "id": "browser",
      "label": "Browser",
      "url": "https://lite.duckduckgo.com/lite/",
      "theme": "blue"
    }
  ]
}
```

## Browser Choice

Default:

```json
"browser_command": "surf",
"browser_args": ["-F"]
```

`surf` is much lighter than Chromium, but some modern sites may not work perfectly. YouTube TV is especially heavy. If a site refuses to work in `surf`, try:

```json
"browser_command": "cog",
"browser_args": ["--platform=x11"]
```

or, as a fallback:

```json
"browser_command": "chromium",
"browser_args": [
  "--no-memcheck",
  "--kiosk",
  "--no-first-run",
  "--disable-dev-shm-usage",
  "--disable-background-networking",
  "--disable-sync",
  "--disable-extensions",
  "--disk-cache-size=16777216",
  "--media-cache-size=16777216"
]
```

On a Pi Zero 2W, `--no-memcheck` is important. Debian's Chromium wrapper otherwise shows a low-memory warning prompt before Chromium reaches kiosk mode.

The launcher itself is light. The opened websites decide how heavy the experience becomes.

## Test On Mac

Mac/headless runs use dry-run mode automatically, so buttons update app state but do not launch a real browser.

```sh
cd /Users/anikeshthakur/Documents/smart-pi-zero
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open:

- `http://localhost:8080/tv`
- `http://localhost:8080/remote`

Click remote buttons. `/tv` should show the last command.

## Docker Compose

Run the project with one command:

```sh
docker compose up -d --build
```

Open:

- `http://localhost:8080/tv`
- `http://localhost:8080/remote`

Stop it:

```sh
docker compose down
```

The default compose file builds a self-contained image with Flask, `xdotool`, `alsa-utils`, and `surf`. On Mac or any headless container it uses dry-run mode automatically, so the UI/API works but it does not try to open a real browser window.

### Docker Compose On Pi With X11

For real browser control from Docker on the Pi, the container needs access to the X server and audio device. Use the Pi compose file:

```sh
cd /home/pi/smart-pi-zero
export DISPLAY=:0
export XAUTHORITY=/home/pi/.Xauthority
docker compose -f docker-compose.pi.yml up -d --build
```

Open from your phone:

- `http://pi-hostname:8080/remote`

Stop it:

```sh
docker compose -f docker-compose.pi.yml down
```

If X access is denied, run this on the Pi host:

```sh
xhost +local:docker
```

Reboot from inside Docker requires extra host permissions and is not enabled by default. Native systemd deployment is cleaner if reboot control must work reliably.

## Native Pi Zero 2W Setup

Install system packages:

```sh
sudo apt update
sudo apt install -y python3 python3-venv python3-pip xserver-xorg xinit openbox x11-xserver-utils xdotool wmctrl unclutter curl alsa-utils surf
```

Optional browser alternatives:

```sh
sudo apt install -y cog
```

Install the app:

```sh
cd /home/pi/smart-pi-zero
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
chmod +x scripts/start-kiosk.sh
```

Edit `config.json` and choose your browser command. Keep `"dry_run": "auto"`; on the Pi with `DISPLAY=:0`, real commands will run.

Run manually:

```sh
python app.py
```

Open from another device:

- `http://pi-hostname:8080/tv`
- `http://pi-hostname:8080/remote`

## Systemd App Service

Review `systemd/pi-tv-launcher.service` and update paths if your user is not `pi`.

```sh
sudo cp systemd/pi-tv-launcher.service /etc/systemd/system/pi-tv-launcher.service
sudo systemctl daemon-reload
sudo systemctl enable --now pi-tv-launcher.service
sudo systemctl status pi-tv-launcher.service
```

## Kiosk Startup

Create `/home/pi/.xinitrc`:

```sh
#!/bin/sh
BROWSER_COMMAND=surf BROWSER_ARGS="-F" /home/pi/smart-pi-zero/scripts/start-kiosk.sh
```

Make it executable:

```sh
chmod +x /home/pi/.xinitrc
```

Start X manually:

```sh
startx
```

If UxPlay or another DRM client blocks Xorg with `drmSetMaster failed`, use the included framebuffer config:

```sh
startx -- -config "$HOME/smart-pi-zero/xorg-fbdev.conf"
```

On the deployed Pi Zero, tty1 autologin can stop UxPlay before starting X and then use this framebuffer config so the TV launcher can coexist with an enabled `uxplay.service`.

## Auto-login On tty1

Create a getty override:

```sh
sudo systemctl edit getty@tty1
```

Add:

```ini
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I $TERM
```

Add to the end of `/home/pi/.profile`:

```sh
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
  startx
fi
```

Reboot:

```sh
sudo reboot
```

## Reboot Permission

The remote reboot button runs:

```sh
sudo systemctl reboot
```

For native Pi deployment, allow it without a password:

```sh
sudo visudo
```

Add:

```text
pi ALL=NOPASSWD: /bin/systemctl reboot, /usr/bin/systemctl reboot
```

## Security

- No arbitrary frontend command execution.
- URLs must start with `http://` or `https://`.
- Set `"pin": "1234"` in `config.json` if you want remote actions protected.
- Keep the service on trusted LAN/Tailscale only.
