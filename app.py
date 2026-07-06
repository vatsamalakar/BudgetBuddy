from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash
)

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from datetime import datetime
from os import environ
from sqlalchemy.exc import IntegrityError

from models import (
    db,
    User,
    Transaction,
    Goal
)

app = Flask(__name__)

app.config["SECRET_KEY"] = environ.get(
    "SECRET_KEY",
    "dev-secret-key"
)

database_url = (
    environ.get("DATABASE_URL")
    or environ.get("POSTGRES_URL")
    or "sqlite:///budget.db"
)

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql://",
        1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except (TypeError, ValueError):
        return None


with app.app_context():
    db.create_all()


# =====================
# HOME
# =====================

@app.route("/")
def home():
    return render_template("home.html")


# =====================
# REGISTER
# =====================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Please fill out all fields")
            return redirect(
                url_for("register")
            )

        existing_user = User.query.filter(
            (User.username == username) |
            (User.email == email)
        ).first()

        if existing_user:
            flash(
                "Username or email already exists"
            )
            return redirect(
                url_for("register")
            )

        hashed_password = generate_password_hash(
            password
        )

        new_user = User(
            username=username,
            email=email,
            password=hashed_password
        )

        try:
            db.session.add(new_user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "Username or email already exists"
            )
            return redirect(
                url_for("register")
            )

        flash("Account created successfully")

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# =====================
# LOGIN
# =====================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter your username and password")
            return redirect(
                url_for("login")
            )

        user = User.query.filter_by(
            username=username
        ).first()

        if user and check_password_hash(
            user.password,
            password
        ):

            login_user(user)

            return redirect(
                url_for("dashboard")
            )

        flash("Invalid credentials")

    return render_template(
        "login.html"
    )


# =====================
# LOGOUT
# =====================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    return redirect(
        url_for("home")
    )


# =====================
# DASHBOARD
# =====================

@app.route("/dashboard")
@login_required
def dashboard():

    transactions = Transaction.query.filter_by(
        user_id=current_user.id
    ).all()

    income = sum(
        t.amount
        for t in transactions
        if t.transaction_type == "Income"
    )

    expenses = sum(
        t.amount
        for t in transactions
        if t.transaction_type == "Expense"
    )

    balance = income - expenses

    return render_template(
        "dashboard.html",
        income=income,
        expenses=expenses,
        balance=balance,
        transactions=transactions
    )


# =====================
# ADD TRANSACTION
# =====================

@app.route(
    "/add_transaction",
    methods=["GET", "POST"]
)
@login_required
def add_transaction():

    if request.method == "POST":

        transaction_type = request.form.get("type", "").strip()
        amount_raw = request.form.get("amount", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        date_raw = request.form.get("date", "").strip()

        if transaction_type not in ("Income", "Expense"):
            flash("Please choose a valid transaction type")
            return redirect(
                url_for("add_transaction")
            )

        if not category:
            flash("Please choose a category")
            return redirect(
                url_for("add_transaction")
            )

        try:
            amount = float(amount_raw)
        except ValueError:
            flash("Please enter a valid amount")
            return redirect(
                url_for("add_transaction")
            )

        if amount <= 0:
            flash("Amount must be greater than zero")
            return redirect(
                url_for("add_transaction")
            )

        try:
            transaction_date = datetime.strptime(
                date_raw,
                "%Y-%m-%d"
            ).date()
        except ValueError:
            flash("Please enter a valid date")
            return redirect(
                url_for("add_transaction")
            )

        transaction = Transaction(
            user_id=current_user.id,
            transaction_type=transaction_type,
            amount=amount,
            category=category,
            description=description,
            date=transaction_date
        )

        db.session.add(transaction)
        db.session.commit()

        flash("Transaction added")

        return redirect(
            url_for("transactions")
        )

    return render_template(
        "add_transaction.html"
    )


# =====================
# TRANSACTIONS
# =====================

@app.route("/transactions")
@login_required
def transactions():

    transactions = (
        Transaction.query
        .filter_by(
            user_id=current_user.id
        )
        .order_by(
            Transaction.date.desc()
        )
        .all()
    )

    return render_template(
        "transactions.html",
        transactions=transactions
    )



# =====================
# REPORTS
# =====================

@app.route("/reports")
@login_required
def reports():

    transactions = Transaction.query.filter_by(
        user_id=current_user.id
    ).all()

    categories = {}

    for t in transactions:

        if t.transaction_type == "Expense":

            categories[t.category] = (
                categories.get(t.category, 0)
                + t.amount
            )

    labels = list(categories.keys())
    values = list(categories.values())

    return render_template(
        "reports.html",
        labels=labels,
        values=values
    )


if __name__ == "__main__":
    app.run(debug=True)
