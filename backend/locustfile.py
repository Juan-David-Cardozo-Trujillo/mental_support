from locust import HttpUser, task, between
import random

class StudentUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        # In a real test, this would authenticate and get a JWT
        pass
        
    @task(3)
    def browse_resources(self):
        self.client.get("/api/v1/resources")
    
    @task(2)
    def check_appointments(self):
        self.client.get("/api/v1/appointments/availability")
    
    @task(1)
    def check_queue_status(self):
        self.client.get("/api/v1/matching/queue-status")

class PeerUser(HttpUser):
    wait_time = between(5, 15)
    
    @task
    def check_dashboard(self):
        self.client.get("/api/v1/peer/dashboard")

class ProfessionalUser(HttpUser):
    wait_time = between(5, 15)
    
    @task
    def check_appointments(self):
        self.client.get("/api/v1/appointments/my")
