pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Setup Environment') {
            steps { sh './setup.sh' }
        }

        stage('Syntax / Sanity Check') {
            steps {
                sh '''
                    .venv/bin/python -m py_compile controller/hybrid_lb_controller.py
                    .venv/bin/python -m py_compile controller/db.py
                    .venv/bin/python -m py_compile controller/routing.py
                    .venv/bin/python -m py_compile backend/server_app.py
                    python3 -m py_compile topology/auto_deploy_topology.py
                '''
            }
        }

        stage('Routing Tests') {
            steps { sh '.venv/bin/python -m unittest discover -s tests -v' }
        }

        stage('Deploy Backend + Dashboard') {
            steps { sh './redeploy.sh' }
        }
    }

    post {
        success { echo 'Deployment successful — controller and dashboard restarted with the verified project setup.' }
        failure { echo 'Build failed — the existing deployment was not overwritten.' }
    }
}
