## Docker and Jenkins

Docker packages the static dashboard and provides repeatable CI validation. The
privileged Mininet, Open vSwitch and Ryu demonstration remains the native WSL
workflow described above.

Start the standalone dashboard:

```bash
docker compose up --build dashboard
```

Run the container validation:

```bash
docker compose --profile test run --rm test
```

Start Jenkins locally after Docker Desktop is running:

```bash
docker compose -f docker-compose.jenkins.yml up --build
```

Open `http://localhost:8080`, complete the first-run Jenkins setup, then create
a **Pipeline** job named `Hybrid-Cloud-SDN`. Choose **Pipeline script from SCM**,
Git, and the repository URL `https://github.com/Armaansalik/Hybrid_cloud_Dynamic_networking.git`.
Set the script path to `Jenkinsfile`. The pipeline installs its own short-lived
CI environment, checks Python syntax, runs the routing tests, and builds the
Docker image when the Jenkins agent can access Docker. It does not start or
replace the live Mininet/Ryu demonstration.
