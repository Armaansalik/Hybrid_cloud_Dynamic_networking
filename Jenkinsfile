pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Syntax check') {
            steps {
                sh '''
                    python3 -m py_compile controller/hybrid_lb_controller.py
                    python3 -m py_compile controller/db.py
                    python3 -m py_compile controller/routing.py
                    python3 -m py_compile backend/server_app.py
                    python3 -m py_compile topology/auto_deploy_topology.py
                '''
            }
        }

        stage('Routing tests') {
            steps { sh 'python3 -m unittest discover -s tests -v' }
        }

        stage('Docker dependency test') {
            when {
                expression {
                    sh(returnStatus: true, script: 'command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1') == 0
                }
            }
            steps { sh 'docker compose --profile test run --rm test' }
        }
    }

    post {
        success { echo 'Validation completed. Deployment remains a deliberate local WSL action.' }
        failure { echo 'Validation failed. The live Mininet/Ryu demonstration was not modified.' }
    }
}
