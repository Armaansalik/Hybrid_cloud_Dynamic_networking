pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Setup Environment') {
            steps {
                sh '''
                    if [ ! -d "venv" ]; then
                        python3.8 -m venv venv
                    fi
                    . venv/bin/activate
                    pip install -r requirements.txt
                '''
            }
        }

        stage('Syntax / Sanity Check') {
            steps {
                sh '''
                    . venv/bin/activate
                    python3 -m py_compile controller/hybrid_lb_controller.py
                    python3 -m py_compile backend/server_app.py
                '''
            }
        }

        stage('Deploy Backend + Dashboard') {
            steps {
                sh './redeploy.sh'
            }
        }
    }

    post {
        success {
            echo 'Deployment successful — controller and dashboard restarted with latest code.'
        }
        failure {
            echo 'Build failed — previous deployment left running, nothing was overwritten.'
        }
    }
}
