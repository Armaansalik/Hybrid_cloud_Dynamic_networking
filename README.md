# Hybrid Cloud-SDN Framework for Dynamic Load-Aware Traffic Routing and Cloud Offloading

A working prototype: an SDN controller (Ryu) that watches live server load on a
private network segment (Mininet) and automatically shifts new requests to a
cloud-hosted backend once local capacity is exceeded.

```
project/
├── README.md
├── requirements.txt
├── topology/
│   └── hybrid_topology.py      # Mininet network: private + cloud segments
├── controller/
│   └── hybrid_lb_controller.py # Ryu app: monitoring + routing + cloud offload
├── backend/
│   └── server_app.py           # Simple service to run on each host
└── testing/
    └── load_test.sh            # Traffic-spike demo script
```

---

## Part A — Before You Even Start (things to know first)

1. **This must run on Linux.** Mininet needs a real or virtual Linux kernel
   (it creates network namespaces). Windows/macOS won't work directly.
   - Easiest path: install **Ubuntu 20.04 or 22.04** in VirtualBox/VMware, or
     use **WSL2** with an Ubuntu distro (Mininet works in WSL2, but a real VM
     is more reliable for a first attempt).
2. **Ryu needs Python 3.8 or 3.9.** Newer Python (3.10+) breaks Ryu's
   `eventlet` dependency in many setups. Check with `python3 --version`
   before installing; if you're on something newer, install `pyenv` or
   `deadsnakes` to get Python 3.9 alongside your system Python.
3. **Work in a Python virtual environment**, not your system Python — Ryu
   and Mininet's Python tooling can conflict with system packages otherwise.
4. **You need root/sudo for Mininet** (it creates virtual interfaces), but
   the Ryu controller itself should run as a normal user, in a separate
   terminal.
5. Decide who on your team owns which piece before you start (matches your
   3-person split): one person on the controller logic, one on
   topology/testing, one on backend services + demo script — but everyone
   should be able to run the whole thing end-to-end.

---

## Part B — Setup (do this once)

```bash
# 1. System packages
sudo apt update
sudo apt install -y mininet python3-venv python3-pip curl

# 2. Get Python 3.9 if you don't already have it (skip if you do)
sudo apt install -y python3.9 python3.9-venv

# 3. Create and activate a virtual environment
python3.9 -m venv venv
source venv/bin/activate

# 4. Install project dependencies
pip install -r requirements.txt

# 5. Sanity check Mininet itself works (separate from your project)
sudo mn --test pingall
```

If step 5 shows `0% dropped`, your base Mininet install is good.

---

## Part C — Build (get each piece running on its own first)

**C1. Start the controller** (Terminal 1, inside your venv, no sudo needed):
```bash
source venv/bin/activate
ryu-manager controller/hybrid_lb_controller.py
```
You should see log lines as switches connect once you start the topology
next — leave this terminal open, you'll watch it during your demo.

**C2. Start the topology** (Terminal 2, needs sudo):
```bash
sudo python3 topology/hybrid_topology.py
```
This drops you into the Mininet CLI (`mininet>`). Check connectivity:
```
mininet> pingall
```
You should see 0% dropped between all hosts. If `h1` can't reach `h2/h3/h4`,
check Terminal 1 for controller errors before continuing.

**C3. Start the backend services** — open an xterm (or use Mininet's `h2 ...`
syntax) for each server host, from inside the Mininet CLI:
```
mininet> h2 python3 backend/server_app.py --name private-A --port 80 &
mininet> h3 python3 backend/server_app.py --name private-B --port 80 &
mininet> h4 python3 backend/server_app.py --name cloud-node --port 80 &
```

**C4. Test a single request** from the client host:
```
mininet> h1 curl http://10.0.0.100/
```
You should get back something like `Handled by backend: private-A ...` and
see a matching `[LOCAL] routing to h2 ...` line in the controller terminal.
That confirms the full path — Mininet → OpenFlow → Ryu → routing decision →
backend response — is working end-to-end.

---

## Part D — Test (prove the dynamic behavior actually works)

```
mininet> h1 bash testing/load_test.sh
```

Watch the **controller terminal** while this runs:
- **Phase 1 (light load):** you should see `[LOCAL] routing to h2/h3 ...`
- **Phase 2 (traffic spike):** once load crosses `LOAD_THRESHOLD_BYTES_PER_SEC`
  in `controller/hybrid_lb_controller.py`, you should see the line switch to
  `[THRESHOLD EXCEEDED] ... CLOUD OFFLOAD to h4`
- **Phase 3 (cooldown):** it should drop back to `[LOCAL]` routing

If the switch to cloud never triggers, lower `LOAD_THRESHOLD_BYTES_PER_SEC`
in the controller file and restart it — the right value depends on your
VM's CPU/network speed, so expect to tune this once during testing.

**For your report/graphs:** redirect the controller's log to a file
(`ryu-manager controller/hybrid_lb_controller.py 2>&1 | tee run.log`) and
also time each `curl` request (`curl -w "%{time_total}\n" -o /dev/null -s ...`)
during the load test — that gives you the response-time data for your
static-vs-dynamic comparison chart.

---

## Part E — Deploy (for your live demo)

You don't need real AWS/GCP/Azure infrastructure to demonstrate the concept
— the whole point is that it's a self-contained, simulator-based prototype.
For your review/viva:

1. Run everything as above, on your laptop, projected on screen.
2. Have **two terminals visible**: the controller's log output, and the
   Mininet CLI where you'll run `load_test.sh`.
3. Narrate the phases as they happen: *"Right now traffic is going to our
   private servers... now I'm triggering a spike... and there — the
   controller just detected the overload and switched new requests to the
   cloud backend automatically."*

**Optional stretch (if you want an actual cloud VM in the demo):**
replace host `h4`'s role with a real free-tier VM (AWS EC2 `t2.micro`,
GCP `e2-micro`, or Azure `B1s`) running `backend/server_app.py`, and have
the controller's cloud-offload path send traffic out your laptop's real
network interface to that VM's public IP instead of to a Mininet host.
This requires NAT/routing configuration beyond this base setup — treat it
as a "future work" extension to mention in your report rather than
something to attempt right before your review.

---

## Known Simplifications (be upfront about these if asked)

- The controller uses a **fixed, hand-mapped topology** (hardcoded ports)
  rather than automatic topology discovery (LLDP) — reasonable for a small,
  controlled testbed, but wouldn't scale to a large or changing network
  as-is.
- The **cloud backend runs in Mininet too** by default — it's a stand-in.
  Swapping it for a real cloud VM (see Part E) is a natural extension.
- The **load threshold is a fixed number you tune manually** — the natural
  next step (and a good "future work" line for your report) is making it
  adaptive, or replacing the scoring rule with a trained model.
