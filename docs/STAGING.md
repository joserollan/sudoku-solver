# Staging (private, via Tailscale)

| | Prod | Staging |
|---|---|---|
| Folder on VM | `~/sudoku-solver` | `~/sudoku-staging` |
| Service | `sudoku` | `sudoku-staging` |
| Listens on | public port | `127.0.0.1:8502` only |
| Reached by | anyone | your Tailscale devices, at `https://<vm-name>.<tailnet>.ts.net` |
| Deployed by | push to `main` | manual run of **Deploy to Staging** |

## One-time setup on the VM

```bash
# 1. Tailscale (log in with the link it prints)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 2. Second checkout + its own virtualenv
git clone "$(git -C ~/sudoku-solver remote get-url origin)" ~/sudoku-staging
python3 -m venv ~/sudoku-staging/venv
~/sudoku-staging/venv/bin/pip install -r ~/sudoku-staging/requirements.txt

# 3. Service (the file is in this repo)
sudo cp ~/sudoku-staging/deploy/sudoku-staging.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sudoku-staging

# 4. Private HTTPS front door, kept across reboots
#    (the first time, it prints a link to enable HTTPS certificates for your tailnet)
sudo tailscale serve --bg 8502
tailscale serve status   # shows the https://... URL
```

`deploy/sudoku-staging.service` only exists once this branch is merged, so for step 3,
run `git -C ~/sudoku-staging checkout claude/staging-tailscale` first, or wait for the merge.

## On your phone

Install the Tailscale app, sign in with the same account, turn it on, and open the URL
printed by `tailscale serve status`.

## Staging a branch

GitHub → **Actions** → **Deploy to Staging** → **Run workflow** → pick the branch → Run.
This works from the GitHub mobile app or the website. The **Run workflow** button only
shows up once this workflow file is on `main`.

## Checks

- `curl -I http://<vm-public-ip>:8502` from outside should fail (nothing listens publicly).
- `sudo journalctl -u sudoku-staging -f` shows the app's logs.
- If the page loads but stays on a spinner, the WebSocket is being rejected. Add
  `--server.enableCORS false --server.enableXsrfProtection false` to `ExecStart`. That's
  acceptable here because only your tailnet can reach staging.
