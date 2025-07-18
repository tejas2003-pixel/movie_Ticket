from flask import Flask, render_template, request, redirect, url_for, session, flash
import hashlib
import boto3  # AWS SDK

# ---------------- AWS Configuration ----------------
AWS_REGION = 'us-east-1'
USERS_TABLE = 'movie_magic_user'
SERVICES_TABLE = 'movie_magic_server'
BOOKINGS_TABLE = 'movie_magic_booking'  # 🔸 Booking table added
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:604665149129:movie_magic_Topic"

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
sns_client = boto3.client('sns', region_name=AWS_REGION)

users_table = dynamodb.Table(USERS_TABLE)
services_table = dynamodb.Table(SERVICES_TABLE)
bookings_table = dynamodb.Table(BOOKINGS_TABLE)  # 🔸 Reference added

# ---------------------------------------------------

app = Flask(__name__)
app.secret_key = 'your-secret-key'

MOVIES = [
    {
        'title': 'Kubera',
        'price': 250,
        'theatres': [
            {'name': 'PVR - GVK Mall', 'price': 250, 'timings': ['6:00 AM', '9:30 AM', '10:30 AM']},
            {'name': 'INOX - Banjara Hills', 'price': 240, 'timings': ['6:00 AM', '9:30 AM', '10:30 AM']}
        ]
    },
    {
        'title': 'DEVARA',
        'price': 280,
        'theatres': [
            {'name': 'Asian - Kukatpally', 'price': 280, 'timings': ['6:00 AM', '9:30 AM', '10:30 AM']},
            {'name': 'Cinepolis - Manjeera Mall', 'price': 280, 'timings': ['6:00 AM', '9:30 AM', '10:30 AM']}
        ]
    },
    {
        'title': 'Animal',
        'price': 300,
        'theatres': [
            {'name': 'Asian - M Cube Mall', 'price': 300, 'timings': ['6:00 AM', '9:30 AM', '10:30 AM']},
            {'name': 'AMBA - RTC X Roads', 'price': 260, 'timings': ['6:00 AM', '9:30 AM', '10:30 AM']}
        ]
    },
    {
        'title': 'Eleven',
        'price': 220,
        'theatres': [
            {'name': 'INOX - Forum Mall', 'price': 220, 'timings': ['6:00 AM', '9:30 AM', '10:30 AM']},
            {'name': 'Cinepolis - Manjeera Mall', 'price': 230, 'timings': ['6:00 AM', '9:30 AM', '10:30 AM']}
        ]
    }
]

users = {}

@app.route('/')
def index_html():
    return render_template('index.html')

@app.route('/home')
def home():
    if 'email' not in session:
        return redirect(url_for('login'))
    return render_template('home.html', movies=MOVIES)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        users[email] = {'name': name, 'password': password}
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        user = users.get(email)
        if user and user['password'] == password:
            session['email'] = email
            session['bookings'] = []
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully')
    return redirect(url_for('index'))

@app.route('/booking', methods=['GET', 'POST'])
@app.route('/booking/<title>', methods=['GET', 'POST'])
def booking(title=None):
    if 'email' not in session:
        return redirect(url_for('login'))

    if not title:
        title = request.args.get('title')

    if not title:
        flash('Movie title is missing.')
        return redirect(url_for('home'))

    movie = next((m for m in MOVIES if m['title'].upper() == title.upper()), None)

    if not movie:
        flash('Movie not found.')
        return redirect(url_for('home'))

    if request.method == 'POST':
        show_time = request.form.get('show_time')
        if not show_time:
            flash('Please select a show time.')
            return render_template('booking.html', movie=movie)
        return redirect(url_for('seating', title=title, show_time=show_time))

    return render_template('booking.html', movie=movie)

@app.route('/seating/<title>', methods=['GET', 'POST'])
def seating(title):
    if 'email' not in session:
        return redirect(url_for('login'))

    movie = next((m for m in MOVIES if m['title'].upper() == title.upper()), None)
    if not movie:
        flash('Movie not found')
        return redirect(url_for('home'))

    if request.method == 'POST':
        seats_raw = request.form.get('seats')
        if not seats_raw:
            flash('No seats selected.')
            return redirect(url_for('seating', title=title))

        selected_seats = seats_raw.split(',')

        total = 0
        seat_list = []
        prices = []

        for seat in selected_seats:
            if ':' not in seat:
                continue
            seat_name, seat_type = seat.split(':')
            seat_list.append(seat_name)

            if seat_type == 'premium':
                price = 250
            elif seat_type == 'gold':
                price = 170
            else:
                flash(f"Unknown seat type: {seat_type}")
                return redirect(url_for('seating', title=title))

            total += price
            prices.append(price)

        price_per_ticket = prices[0] if prices else 0

        booking = {
            'movie': movie['title'],
            'seats': ', '.join(seat_list),
            'price': price_per_ticket,
            'total': total
        }

        session.setdefault('bookings', []).append(booking)
        session.modified = True

        # Optional: Send confirmation via SNS
        try:
            sns_client.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=f"Booking Confirmed for {movie['title']} - Seats: {seat_list}",
                Subject="Movie Booking Confirmation"
            )
        except Exception as e:
            print("SNS publish failed:", e)

        return redirect(url_for('tickets', title=title, seats=','.join(seat_list)))

    return render_template('seating.html', movie=movie)

@app.route('/tickets')
def tickets():
    title = request.args.get('title')
    seats_raw = request.args.get('seats', '')
    seat_list = [s.strip() for s in seats_raw.split(',') if s.strip()]

    total = 0
    for seat in seat_list:
        if ':' in seat:
            seat_num, category = seat.split(':')
            if category == 'premium':
                total += 250
            elif category == 'gold':
                total += 170
        else:
            total += 200

    return render_template('tickets.html', title=title, seats=", ".join([s.split(':')[0] for s in seat_list]), total=total)

@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('login'))

    bookings = session.get('bookings', [])
    return render_template('dashboard.html', bookings=bookings)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# ---------------- For EC2 ----------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)