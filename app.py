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
    return User.query.get(int(user_id))


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

        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

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

        db.session.add(new_user)
        db.session.commit()

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

        username = request.form["username"]
        password = request.form["password"]

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

        transaction = Transaction(
            user_id=current_user.id,
            transaction_type=request.form["type"],
            amount=float(
                request.form["amount"]
            ),
            category=request.form["category"],
            description=request.form[
                "description"
            ],
            date=datetime.strptime(
                request.form["date"],
                "%Y-%m-%d"
            ).date()
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
