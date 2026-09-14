import json
import random
from datetime import datetime, timedelta

DATA_DIR = "car-rental-final/data"

# Local seed data generator for testing and initial database imports.
brands = {
    "Honda": ["Civic", "City", "BR-V"],
    "Toyota": ["Corolla", "Yaris", "Fortuner", "Prado", "Land Cruiser"],
    "Suzuki": ["Alto", "Cultus", "Swift"],
    "Hyundai": ["Elantra", "Tucson"],
    "Changan": ["Alsvin", "Oshan X7"],
    "BMW": ["3 Series"],
    "Mercedes": ["C-Class"],
    "Nissan": ["Dayz", "Note"]
}

cities = ["Lahore", "Karachi", "Islamabad", "Faisalabad", "Multan"]

def generate_cars(n=200):
    cars = []
    for i in range(n):
        brand = random.choice(list(brands.keys()))
        model = random.choice(brands[brand])

        car = {
            "_id": f"CAR{i+1:03}",
            "brand": brand,
            "model": model,
            "year": random.randint(2018, 2024),
            "category": random.choice(["Sedan", "SUV", "Hatchback"]),
            "price_per_day": random.randint(3000, 20000),
            "city": random.choice(cities),
            "features": ["AC", "ABS", "Airbags", "Bluetooth"],
            "ratings": [random.randint(3, 5) for _ in range(3)],
            "availability": True,
            "created_at": str(datetime.now())
        }
        cars.append(car)
    return cars


def generate_users(n=3000):
    users = []

    users.append({
        "_id": "USR0000",
        "name": "Admin",
        "email": "admin@gmail.com",
        "password": "hashed_password",
        "role": "admin",
        "created_at": str(datetime.now())
    })

    for i in range(n):
        user = {
            "_id": f"USR{i+1:04}",
            "name": f"User{i}",
            "email": f"user{i}@gmail.com",
            "password": "hashed_password",
            "role": "user",
            "created_at": str(datetime.now())
        }
        users.append(user)

    return users


def generate_bookings(users, cars, n=300):
    bookings = []

    for i in range(n):
        user = random.choice(users)
        car = random.choice(cars)

        start = datetime.now() + timedelta(days=random.randint(1, 30))
        end = start + timedelta(days=random.randint(1, 5))

        booking = {
            "_id": f"BKG{i+1:04}",
            "user_id": user["_id"],
            "car_id": car["_id"],
            "start_date": str(start),
            "end_date": str(end),
            "status": random.choice(["confirmed", "pending", "completed"]),
            "payment_status": random.choice(["paid", "unpaid"]),
            "total_price": random.randint(5000, 50000),
            "version": 1,
            "created_at": str(datetime.now())
        }

        bookings.append(booking)

    return bookings


def generate_reviews(users, cars, n=200):
    reviews = []

    for i in range(n):
        review = {
            "_id": f"REV{i+1:04}",
            "user_id": random.choice(users)["_id"],
            "car_id": random.choice(cars)["_id"],
            "rating": random.randint(3, 5),
            "comment": "Good experience",
            "created_at": str(datetime.now())
        }

        reviews.append(review)

    return reviews


def generate_payments(bookings):
    payments = []

    for i, booking in enumerate(bookings):
        payment = {
            "_id": f"PAY{i+1:04}",
            "booking_id": booking["_id"],
            "amount": booking["total_price"],
            "status": booking["payment_status"],
            "method": random.choice(["card", "cash"]),
            "created_at": str(datetime.now())
        }

        payments.append(payment)

    return payments


def save_json(data, filename):
    with open(f"{DATA_DIR}/{filename}", "w") as f:
        json.dump(data, f, indent=4)


def main():
    # Generate related collections in one pass so IDs stay consistent.
    cars = generate_cars()
    users = generate_users()
    bookings = generate_bookings(users, cars)
    reviews = generate_reviews(users, cars)
    payments = generate_payments(bookings)

    save_json(cars, "cars.json")
    save_json(users, "users.json")
    save_json(bookings, "bookings.json")
    save_json(reviews, "reviews.json")
    save_json(payments, "payments.json")

    print("All datasets generated successfully.")


if __name__ == "__main__":
    main()
