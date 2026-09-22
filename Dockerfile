# Docker supports repeatable dashboard and CI runs. Run Mininet/OVS/Ryu natively in WSL.
FROM python:3.8-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY controller ./controller
COPY dashboard ./dashboard
COPY tests ./tests
COPY topology ./topology

EXPOSE 8081

CMD ["python", "-m", "http.server", "8081", "--directory", "dashboard"]
