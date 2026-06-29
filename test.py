import requests

tests = [
    {
        "label": "Clearly AI",
        "text": "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.",
        "creator_id": "test-user-1"
    },
    {
        "label": "Clearly human",
        "text": "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there",
        "creator_id": "test-user-2"
    },
    {
        "label": "Borderline formal human",
        "text": "The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations.",
        "creator_id": "test-user-3"
    },
    {
        "label": "Borderline edited AI",
        "text": "I've been thinking a lot about remote work lately. There are genuine tradeoffs — flexibility and no commute on one side, isolation and blurred work-life boundaries on the other. Studies show productivity varies widely by individual and role type.",
        "creator_id": "test-user-4"
    }
]

for t in tests:
    response = requests.post("http://127.0.0.1:5000/submit", json=t)
    data = response.json()
    print(f"--- {t['label']} ---")
    print(f"  Attribution:  {data['attribution']}")
    print(f"  Confidence:   {data['confidence']}")
    print(f"  Label:        {data['label']}")
    print(f"  Content ID:   {data['content_id']}")
    print()