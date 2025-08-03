from flask import Flask, request, jsonify
import sqlite3
import math
from datetime import datetime, timedelta

app = Flask(__name__)

# Secure SQLite setup (in-memory for MVP, file-based in production)
def init_db():
    conn = sqlite3.connect(':memory:')  # Switch to 'cbam.db' for persistence
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS venues (
        id INTEGER PRIMARY KEY,
        name TEXT,
        address TEXT,
        lat REAL,
        lon REAL,
        time TEXT,
        notes TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS skips (
        user_id TEXT,
        venue_id INTEGER,
        skip_type TEXT,
        reminder TEXT
    )''')
    # Sample Manhattan venues (Aug 3, 2025)
    venues = [
        (1, 'St. Marks Comedy Club', '12 St Marks Pl, New York, NY 10003', 40.7282, -73.9872, '16:30', '$5, beginner-friendly'),
        (2, 'Grisly Pear Comedy Club', '243 West 54th St, New York, NY 10019', 40.7648, -73.9838, '17:00', 'Free for performers'),
        (3, 'Peoples Improv Theater', '123 E 24th St, New York, NY 10010', 40.7403, -73.9860, '18:30', 'Inclusive, $0-5'),
        (4, 'West Side Comedy Club', '201 W 75th St, New York, NY 10023', 40.7809, -73.9798, '20:00', '$5 + drink')
    ]
    c.executemany('INSERT OR REPLACE INTO venues VALUES (?, ?, ?, ?, ?, ?, ?)', venues)
    conn.commit()
    return conn

# Haversine distance (miles)
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

# Insertion Heuristic for itinerary
def generate_itinerary(form):
    conn = init_db()
    c = conn.cursor()
    c.execute('SELECT * FROM skips WHERE user_id = ?', ('user1',))  # Mock user
    skips = {row[1]: row[2] for row in c.fetchall()}
    today = datetime.strptime(form['date'], '%Y-%m-%d')
    week_end = (today + timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Filter venues
    c.execute('SELECT * FROM venues WHERE id NOT IN (SELECT venue_id FROM skips WHERE skip_type IN (?, ?))', ('one_time', 'forever'))
    c.execute('SELECT * FROM venues WHERE id NOT IN (SELECT venue_id FROM skips WHERE skip_type = ? AND ? <= ?)', ('week', form['date'], week_end))
    venues = c.fetchall()
    
    # Parse start time
    start_time = datetime.strptime(f"{form['date']} {form['startTime']}", '%Y-%m-%d %H:%M')
    start_lat, start_lon = 40.7359, -73.9911  # Union Square
    max_spots = int(form['maxSpots'])
    buffer = int(form['buffer'])
    transport = form['transport']
    
    itinerary = []
    current_time = start_time
    current_lat, current_lon = start_lat, start_lon
    
    # Insertion Heuristic
    while venues and len(itinerary) < max_spots:
        best_venue = None
        best_cost = float('inf')
        best_travel = ''
        
        for venue in venues:
            venue_id, name, address, lat, lon, time_str, notes = venue
            gig_time = datetime.strptime(f"{form['date']} {time_str}", '%Y-%m-%d %H:%M')
            if gig_time < current_time + timedelta(minutes=buffer):
                continue
            dist = haversine(current_lat, current_lon, lat, lon)
            if 'walk' in transport and dist <= 1:
                travel_time = int(dist / 0.05)  # 3 mph walking
                travel_mode = f"{dist:.1f} mi walk ({travel_time} min)"
            elif 'subway' in transport and dist <= 3:
                travel_time = int(dist / 0.5) + 5  # Subway + wait
                travel_mode = f"{dist:.1f} mi subway ({travel_time} min)"
            else:
                continue
            if gig_time >= current_time + timedelta(minutes=travel_time + buffer):
                cost = travel_time + (gig_time - (current_time + timedelta(minutes=travel_time))).seconds / 60
                if cost < best_cost:
                    best_cost = cost
                    best_venue = venue
                    best_travel = travel_mode
        
        if best_venue:
            itinerary.append({
                'venueId': best_venue[0],
                'name': best_venue[1],
                'address': best_venue[2],
                'time': best_venue[5],
                'travel': best_travel,
                'notes': best_venue[6]
            })
            current_time = datetime.strptime(f"{form['date']} {best_venue[5]}", '%Y-%m-%d %H:%M') + timedelta(minutes=5)  # Assume 5 min set
            current_lat, current_lon = best_venue[3], best_venue[4]
            venues.remove(best_venue)
    
    conn.close()
    return itinerary

@app.route('/generate', methods=['POST'])
def generate():
    form = request.json
    itinerary = generate_itinerary(form)
    return jsonify({'itinerary': itinerary})

@app.route('/skip', methods=['POST'])
def skip_venue():
    data = request.json
    conn = init_db()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO skips (user_id, venue_id, skip_type, reminder) VALUES (?, ?, ?, ?)',
              ('user1', data['venueId'], data['skipType'], data.get('reminder')))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/outreach', methods=['POST'])
def outreach():
    data = request.json
    venue = data['venue']
    user = data['user']
    template = f"""Subject: Open Mic Slot at {venue['name']}?

Hi [Booker],

I’m {user['name']}, a {user['experience']} comic with a 5-min set. I’d love to perform at your {venue['time']} open mic on August 3, 2025, at {venue['name']}. My material is clean and crowd-friendly, with recent spots at [e.g., The Tiny Cupboard]. Any slots available? I can send a clip if needed!

Thanks,
{user['name']}
{user['email']}

[Generated in ~0.5s | Edit before sending | Save securely or delete]"""
    return jsonify({'template': template})

if __name__ == '__main__':
    app.run(debug=True)