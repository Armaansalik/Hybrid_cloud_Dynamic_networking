# Hybrid Cloud-SDN

This is the single, self-contained WSL project for the Hybrid Cloud-SDN demo.
Keep all commands and project files in `~/HybridCloudSDN`; do not run a copy
from Windows drives or the former `~/projects/hybrid-cloud-sdn-project` folder.

## Folder layout

```
HybridCloudSDN/
├── .venv/                 # project-only Python 3.8 environment
├── backend/               # simulated private and cloud services
├── controller/            # Ryu routing policy, REST API, SQLite layer
├── dashboard/             # static live dashboard
├── data/                  # runtime SQLite database
├── logs/                  # controller and dashboard logs
├── testing/               # repeatable traffic demonstration
├── topology/              # Mininet topology and automatic service startup
├── setup.sh               # one-time setup
├── start_all.sh           # normal demo startup
└── redeploy.sh            # controller/dashboard restart only
```

## One-time setup

Run these commands from WSL:

```bash
cd ~/HybridCloudSDN
chmod +x setup.sh start_all.sh redeploy.sh testing/demo_cycle.sh
./setup.sh
```

The environment is created inside `.venv`, so it does not depend on a Python
environment stored elsewhere.

## Run the demo

Terminal 1:

```bash
cd ~/HybridCloudSDN
./start_all.sh
```

The script starts Ryu on API port `8082`, the dashboard on port `8081`, and
then opens the Mininet prompt. Services and iperf are started automatically.

At the `mininet>` prompt run:

```bash
h1 curl -sS --connect-timeout 5 http://10.0.0.100/
h1 bash testing/demo_cycle.sh
```

Open <http://localhost:8081/index.html> in Windows. The dashboard reads its
controller data from `http://127.0.0.1:8082`.

## Expected checks

- The first curl returns JSON with `served_by: private-gpu-A` or `private-gpu-B`.
- During the traffic spike, controller logs show gradual cloud offload to `h4`.
- After the spike, routing returns to a private backend.
- The dashboard displays controller status rather than `controller unreachable`.

## Important implementation note

The private and cloud areas are logical segments in this Mininet proof of
concept. Access-port tagging is not applied because the controller
rewrites the virtual service address; adding the old tags caused return
traffic to be discarded and made `h1 curl http://10.0.0.100/` time out.
