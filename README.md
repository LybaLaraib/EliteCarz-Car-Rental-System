# EliteCarz — A MongoDB-Driven Car Rental Management System

A full-stack car rental management system built with **Flask** and **MongoDB Atlas**, developed as the final project for *CSC 316 – Advanced Database Systems* at COMSATS University Islamabad.

The system automates car rental operations — vehicle management, customer bookings, payments, and reviews — while demonstrating core Advanced Database Systems concepts on a real-world application.

   📄 [Full Project Report](Project_Documentation_ADB.pdf)

## Features

- **CRUD operations** across cars, bookings, users, payments, and reviews
- **Aggregation pipelines** powering analytics dashboards (monthly revenue, top-performing cars, revenue by city)
- **Multi-document transactions** for atomic booking + payment processing
- **Concurrency control** using both optimistic locking (versioned documents) and pessimistic locking (a dedicated locks collection)
- **MongoDB Views and Materialized Views** for efficient reporting
- **Role-based access control** (Admin / User / Guest)
- **Security**: salted password hashing (bcrypt), NoSQL-injection-safe queries
- Admin dashboard with revenue charts, booking management, and review moderation

## Tech Stack

- **Backend:** Python, Flask
- **Database:** MongoDB Atlas
- **Frontend:** HTML, CSS, JavaScript, Chart.js
- **Auth/Security:** bcrypt

## Project Structure

- **app.py** — Application entry point
- **config.py** — Environment configuration
- **seed.py** — Populates the database with sample data
- **generate_dataset.py** — Generates sample JSON datasets
- **routes/** — Flask route blueprints (auth, admin, booking, review, user)
- **database/** — Aggregation pipelines, indexes, views
- **utils/** — Auth, DB connection, locking, helper functions
- **templates/** — HTML templates
- **static/** — CSS and JS assets
- **data/** — Sample seed data (cars, users, bookings, payments, reviews)

## Setup & Running Locally

1. Clone the repository and install dependencies:

pip install -r requirements.txt


2. Create a `.env` file in the project root with your own MongoDB Atlas credentials:

MONGO_URI=your_mongodb_connection_string
DB_NAME=CarRentalFinal
SECRET_KEY=your_secret_key


3. Populate the database with sample data:

python seed.py


4. Run the application:

python app.py

   Visit `http://127.0.0.1:5000`

### Test credentials
- **Admin login:** username `admin`, password `admin123`
- **User login:** sign up for a new account via the Sign Up page (seeded demo accounts use placeholder passwords and are not meant for direct login)

### Note
Car listing images are excluded from this repository to keep it lightweight. The app expects images at `static/images/cars/` to display car photos if run locally.

## Team

Built by **Laiba Laraib** and **Muhammad Usama** as a team project for CSC 316 – Advanced Database Systems, COMSATS University Islamabad (May 2026).
