# ======================================================
#                 IMPORTS
# ======================================================
from flask import Flask, render_template, request, redirect, session, flash
from db_config import get_connection
import matplotlib.pyplot as plt
import os

# ======================================================
#                 APP INITIALIZATION
# ======================================================
app = Flask(__name__)
app.secret_key = "bloodbank_secret_key"   # Required for session & flash


# ======================================================
#                 HOME PAGE
# ======================================================
@app.route("/")
def home():
    return render_template("index.html")


# ======================================================
#                 LOGIN SYSTEM
# ======================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (username, password)
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            session["user"] = user["username"]
            flash("Login Successful!", "success")
            return redirect("/dashboard")
        else:
            flash("Invalid Username or Password!", "danger")
            return redirect("/login")

    return render_template("login.html")


# ======================================================
#                 LOGOUT
# ======================================================
@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged Out Successfully!", "info")
    return redirect("/")


# ======================================================
#                 DASHBOARD
# ======================================================
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    # Total donors
    cursor.execute("SELECT COUNT(*) FROM donors")
    donors = cursor.fetchone()[0]

    # Total requests
    cursor.execute("SELECT COUNT(*) FROM blood_requests")
    requests_count = cursor.fetchone()[0]

    # Total available blood units
    cursor.execute("SELECT SUM(units_available) FROM blood_inventory")
    total_units = cursor.fetchone()[0] or 0
    
    # NEW: Blood Demand Summary
    cursor.execute("""
        SELECT blood_group, SUM(units_required)
        FROM blood_requests
        GROUP BY blood_group
    """)
    demand_summary = cursor.fetchall()

    conn.close()

    return render_template("dashboard.html",
                           donors=donors,
                           requests=requests_count,
                           total_units=total_units,
                           demand_summary=demand_summary)


# ======================================================
#                 ADD BLOOD REQUEST
# ======================================================
@app.route("/add_request", methods=["GET", "POST"])
def add_request():

    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":

        patient_name = request.form["patient_name"]
        blood_group = request.form["blood_group"]
        units_required = int(request.form["units_required"])
    

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO blood_requests
            (patient_name, blood_group, units_required, status)
            VALUES (%s, %s, %s, 'Pending') """,
            (patient_name, blood_group, units_required))

        conn.commit()
        conn.close()

        flash("Blood Request Added Successfully!", "success")
        return redirect("/requests")

    return render_template("add_request.html")


# ======================================================
#                 VIEW ALL REQUESTS
# ======================================================
@app.route("/requests")
def view_requests():

    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM blood_requests")
    request_data = cursor.fetchall()

    conn.close()

    return render_template("requests.html", requests=request_data)


# ======================================================
#                 APPROVE / ISSUE BLOOD
# ======================================================
@app.route("/issue_blood/<int:request_id>")
def issue_blood(request_id):

    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)

    # Fetch request details
    cursor.execute("""
        SELECT blood_group, units_required, status
        FROM blood_requests
        WHERE request_id = %s
    """, (request_id,))

    request_data = cursor.fetchone()

    if not request_data:
        conn.close()
        flash("Request Not Found!", "danger")
        return redirect("/requests")

    if request_data["status"] != "Pending":
        conn.close()
        flash("Request Already Processed!", "warning")
        return redirect("/requests")

    blood_group = request_data["blood_group"]
    units = request_data["units_required"]

    # Check stock availability
    cursor.execute("""
        SELECT units_available
        FROM blood_inventory
        WHERE blood_group = %s
    """, (blood_group,))

    stock = cursor.fetchone()

    if stock and stock["units_available"] >= units:

        # Deduct stock
        cursor.execute("""
            UPDATE blood_inventory
            SET units_available = units_available - %s
            WHERE blood_group = %s
        """, (units, blood_group))

        # Update request status
        cursor.execute("""
            UPDATE blood_requests
            SET status = 'Approved'
            WHERE request_id = %s
        """, (request_id,))

        conn.commit()
        flash("Blood Issued Successfully!", "success")

    else:
        flash("Insufficient Stock!", "danger")

    conn.close()
    return redirect("/requests")


# ======================================================
#                 REJECT REQUEST
# ======================================================
@app.route("/reject_request/<int:request_id>")
def reject_request(request_id):

    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE blood_requests
        SET status = 'Rejected'
        WHERE request_id = %s
    """, (request_id,))

    conn.commit()
    conn.close()

    flash("Request Rejected!", "info")
    return redirect("/requests")


# ======================================================
#                 DONORS PAGE
# ======================================================
@app.route("/donors")
def donors():

    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    # Get all donors
    cursor.execute("SELECT * FROM donors")
    donors = cursor.fetchall()

    # Total donors
    cursor.execute("SELECT COUNT(*) FROM donors")
    total_donors = cursor.fetchone()[0]

    # Most common blood group
    cursor.execute("""
        SELECT blood_group, COUNT(*) as total
        FROM donors
        GROUP BY blood_group
        ORDER BY total DESC
        LIMIT 1
    """)
    result = cursor.fetchone()

    if result:
        common_blood = result[0]
    else:
        common_blood = "N/A"

    conn.close()

    return render_template(
        "donors.html",
        donors=donors,
        total_donors=total_donors,
        common_blood=common_blood
    )
# ======================================================
#                 ADD DONOR
# ======================================================
@app.route('/add_donor', methods=['GET', 'POST'])
def add_donor():

    # Check login session (same security as other pages)
    if "user" not in session:
        return redirect("/login")

    if request.method == 'POST':

        # Get form data
        donor_name = request.form['donor_name']
        blood_group = request.form['blood_group']
        contact = request.form['contact']

        # Database connection using your existing function
        conn = get_connection()
        cursor = conn.cursor()

        # Insert donor into database
        cursor.execute("""
            INSERT INTO donors (donor_name, blood_group, contact)
            VALUES (%s, %s, %s)
        """, (donor_name, blood_group, contact))

        conn.commit()
        conn.close()

        # Success message
        flash("Donor Added Successfully!", "success")

        # Redirect to donors list
        return redirect("/donors")

    # If GET request → open Add Donor page
    return render_template('add_donor.html')

# ======================================================
#                 INVENTORY PAGE
# ======================================================
@app.route("/inventory")
def inventory():

    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Inventory table
    cursor.execute("SELECT * FROM blood_inventory")
    inventory = cursor.fetchall()

    # Total units
    cursor.execute("SELECT SUM(units_available) AS total_units FROM blood_inventory")
    result = cursor.fetchone()
    total_units = result['total_units'] or 0


    # Highest stock blood group
    cursor.execute("""
        SELECT blood_group
        FROM blood_inventory
        ORDER BY units_available DESC
        LIMIT 1
    """)
    highest_stock = cursor.fetchone()['blood_group']


    # Lowest stock blood group
    cursor.execute("""
        SELECT blood_group
        FROM blood_inventory
        ORDER BY units_available ASC
        LIMIT 1
    """)
    lowest_stock = cursor.fetchone()['blood_group']

    # Low stock groups
    cursor.execute("""
        SELECT blood_group
        FROM blood_inventory
        WHERE units_available < 5
    """)
    low_stock = cursor.fetchall()

    conn.close()

    return render_template(
        "inventory.html",
        inventory=inventory,
        total_units=total_units,
        highest_stock=highest_stock,
        lowest_stock=lowest_stock,
        low_stock=low_stock
    )
# ======================================================
#                 ADD / UPDATE INVENTORY
# ======================================================
@app.route("/add_inventory", methods=["GET", "POST"])
def add_inventory():

    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":

        blood_group = request.form["blood_group"]
        units = int(request.form["units"])

        conn = get_connection()
        cursor = conn.cursor(buffered=True)

        # Check if blood group already exists
        cursor.execute("""
            SELECT * FROM blood_inventory
            WHERE blood_group = %s
        """, (blood_group,))

        existing = cursor.fetchone()

        if existing:
            # Update existing stock
            cursor.execute("""
                UPDATE blood_inventory
                SET units_available = units_available + %s
                WHERE blood_group = %s
            """, (units, blood_group))
        else:
            # Insert new blood group
            cursor.execute("""
                INSERT INTO blood_inventory
                (blood_group, units_available)
                VALUES (%s, %s)
            """, (blood_group, units))

        conn.commit()
        conn.close()

        flash("Inventory Updated Successfully!", "success")
        return redirect("/inventory")

    return render_template("add_inventory.html")

# ======================================================
#                 HOSPITALS PAGE
# ======================================================
@app.route("/hospitals")
def hospitals():

    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM hospitals")
    hospital_data = cursor.fetchall()

    conn.close()

    return render_template("hospitals.html", hospitals=hospital_data)

# ======================================================
# ADD HOSPITAL
# ======================================================

@app.route("/add_hospital", methods=["GET", "POST"])
def add_hospital():
    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":
        hospital_name = request.form["hospital_name"]
        city = request.form["city"]
        contact = request.form["contact"]

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO hospitals (hospital_name, city, contact)
            VALUES (%s, %s, %s)
        """, (hospital_name, city, contact))

        conn.commit()
        conn.close()

        flash("Hospital Added Successfully!", "success")
        return redirect("/hospitals")

    return render_template("add_hospital.html")

# ======================================================
#                 ANALYTICS GRAPH
# ======================================================
@app.route("/analytics")
def analytics():

    if "user" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    # 1️⃣ Total Donors
    cursor.execute("SELECT COUNT(*) FROM donors")
    total_donors = cursor.fetchone()[0]

    # 2️⃣ Total Hospitals
    cursor.execute("SELECT COUNT(*) FROM hospitals")
    total_hospitals = cursor.fetchone()[0]

    # 3️⃣ Blood Group Demand Summary
    cursor.execute("""
        SELECT blood_group, SUM(units_required)
        FROM blood_requests
        GROUP BY blood_group
        ORDER BY SUM(units_required) DESC
    """)
    
    demand_summary = cursor.fetchall()

    blood_groups = [row[0] for row in demand_summary]
    units = [row[1] for row in demand_summary]

    # 4️⃣ Hospital Ranking (RANK function)
    cursor.execute("""
        SELECT h.hospital_name,
               SUM(r.units_required) AS total_units,
               RANK() OVER (ORDER BY SUM(r.units_required) DESC) AS rank_position
        FROM blood_requests r
        JOIN hospitals h ON r.hospital_id = h.hospital_id
        GROUP BY h.hospital_name
    """)
    
    hospital_ranking = cursor.fetchall()

    # 5️⃣ Stock Status using CASE
    cursor.execute("""
        SELECT blood_group,
        CASE 
            WHEN units_available < 5 THEN 'Low Stock'
            ELSE 'Sufficient'
        END
        FROM blood_inventory
    """)
    
    stock_status = cursor.fetchall()

    # 6️⃣ Monthly Requests (Line Chart)
    cursor.execute("""
        SELECT DATE_FORMAT(request_date, '%Y-%m'),
               SUM(units_required)
        FROM blood_requests
        GROUP BY DATE_FORMAT(request_date, '%Y-%m')
        ORDER BY DATE_FORMAT(request_date, '%Y-%m')
    """)

    monthly_data = cursor.fetchall()

    months = [row[0] for row in monthly_data]
    monthly_units = [row[1] for row in monthly_data]

    conn.close()

    return render_template(
        "analytics.html",
        total_donors=total_donors,
        total_hospitals=total_hospitals,
        hospital_ranking=hospital_ranking,
        stock_status=stock_status,
        blood_groups=blood_groups,
        units=units,
        months=months,
        monthly_units=monthly_units
    )

# ======================================================
#                 DATABASE CONNECTION TEST
# ======================================================
@app.route("/test_connection")
def test_connection():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        return "✅ Database Connected Successfully!"
    except Exception as e:
        return f"❌ Connection Failed: {e}"

print(app.url_map)

# ======================================================
#                 RUN APPLICATION
# ======================================================
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)