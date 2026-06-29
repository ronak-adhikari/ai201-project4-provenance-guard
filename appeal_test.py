import requests

response = requests.post(
    "http://127.0.0.1:5000/appeal",
    json={
        "content_id": "98dfa456-afff-4756-b2c1-4f8a283aafe3",
        "creator_reasoning": "I wrote this myself from personal experience. I am an economics researcher and my academic writing style may appear more formal than typical, which could trigger false AI detection."
    }
)
print("Status code:", response.status_code)
print("Response:", response.json())