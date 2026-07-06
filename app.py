from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    session
)

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
    UserMixin
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from datetime import datetime
from os import environ
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

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
)

DEMO_MODE = bool(environ.get("VERCEL") and not database_url)

if not database_url:
    database_url = "sqlite:///:memory:" if DEMO_MODE else "sqlite:///budget.db"

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


class DemoUser(UserMixin):
    def __init__(self, username, email=""):
        self.id = username
        self.username = username
        self.email = email


@login_manager.user_loader
def load_user(user_id):
    if DEMO_MODE:
        account = session.get("account")

        if account and account.get("username") == user_id:
            return DemoUser(
                account["username"],
                account.get("email", "")
            )

        return None

    try:
        return User.query.get(int(user_id))
    except (TypeError, ValueError):
        return None


if not DEMO_MODE:
    with app.app_context():
        db.create_all()


def get_demo_transactions():
    return session.get("transactions", [])


def transaction_value(transaction, name):
    if isinstance(transaction, dict):
        return transaction[name]

    return getattr(transaction, name)


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

        if DEMO_MODE:
            account = session.get("account")

            if account and (
                account.get("username") == username
                or account.get("email") == email
            ):
                flash(
                    "Username or email already exists"
                )
                return redirect(
                    url_for("register")
                )

            session["account"] = {
                "username": username,
                "email": email,
                "password": generate_password_hash(password)
            }
            session["transactions"] = []
            login_user(DemoUser(username, email))

            flash("Account created successfully")

            return redirect(
                url_for("dashboard")
            )

        try:
            existing_user = User.query.filter(
                (User.username == username) |
                (User.email == email)
            ).first()
        except SQLAlchemyError:
            db.session.rollback()
            flash("Database error. Please try again.")
            return redirect(
                url_for("register")
            )

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
        except SQLAlchemyError:
            db.session.rollback()
            flash("Database error. Please try again.")
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

        if DEMO_MODE:
            account = session.get("account")

            if account and account.get("username") == username:
                if check_password_hash(
                    account["password"],
                    password
                ):
                    login_user(
                        DemoUser(
                            account["username"],
                            account.get("email", "")
                        )
                    )

                    return redirect(
                        url_for("dashboard")
                    )

            flash("Invalid credentials")
            return render_template(
                "login.html"
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

    if DEMO_MODE:
        transactions = get_demo_transactions()
    else:
        transactions = Transaction.query.filter_by(
            user_id=current_user.id
        ).all()

    income = sum(
        transaction_value(t, "amount")
        for t in transactions
        if transaction_value(t, "transaction_type") == "Income"
    )

    expenses = sum(
        transaction_value(t, "amount")
        for t in transactions
        if transaction_value(t, "transaction_type") == "Expense"
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

        if DEMO_MODE:
            transactions = get_demo_transactions()
            transactions.append(
                {
                    "id": len(transactions) + 1,
                    "transaction_type": transaction_type,
                    "amount": amount,
                    "category": category,
                    "description": description,
                    "date": transaction_date.isoformat()
                }
            )
            session["transactions"] = transactions
            session.modified = True

            flash("Transaction added")

            return redirect(
                url_for("transactions")
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

    if DEMO_MODE:
        transactions = sorted(
            get_demo_transactions(),
            key=lambda transaction: transaction["date"],
            reverse=True
        )
    else:
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

    if DEMO_MODE:
        transactions = get_demo_transactions()
    else:
        transactions = Transaction.query.filter_by(
            user_id=current_user.id
        ).all()

    categories = {}

    for t in transactions:

        if transaction_value(t, "transaction_type") == "Expense":

            category = transaction_value(t, "category")

            categories[category] = (
                categories.get(category, 0)
                + transaction_value(t, "amount")
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
