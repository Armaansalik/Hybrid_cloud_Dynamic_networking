pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    environment {
        VENV_DIR = '.ci-venv'
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Create CI environment') {
            steps {
                sh '''
                    python3 -m venv "$VENV_DIR"
                    "$VENV_DIR/bin/python" -m pip install --upgrade pip
                    "$VENV_DIR/bin/python" -m pip install -r requirements.txt
                '''
            }
        }

        stage('Syntax check') {
            steps {
                sh '''
                    "$VENV_DIR/bin/python" -m py_compile controller/hybrid_lb_controller.py
                    "$VENV_DIR/bin/python" -m py_compile controller/db.py
                    "$VENV_DIR/bin/python" -m py_compile controller/routing.py
                    "$VENV_DIR/bin/python" -m py_compile backend/server_app.py
                    "$VENV_DIR/bin/python" -m py_compile topology/auto_deploy_topology.py
                '''
            }
        }

        stage('Routing tests') {
            steps { sh '"$VENV_DIR/bin/python" -m unittest discover -s tests -v' }
        }

        stage('Docker build') {
            when {
                expression {
                    sh(returnStatus: true, script: 'command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1') == 0
                }
            }
            steps { sh 'docker build --tag hybrid-cloud-sdn-ci:${BUILD_NUMBER} .' }
        }
    }

    post {
        always { sh 'rm -rf "$VENV_DIR"' }
        success { echo 'Validation completed. Deployment remains a deliberate local WSL action.' }
        failure { echo 'Validation failed. The live Mininet/Ryu demonstration was not modified.' }
    }
}
