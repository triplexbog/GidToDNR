from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Location, Category, Review, Favorite
from flask import jsonify
from flask_login import current_user
from functools import wraps

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///dnr.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'supersecret'

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def index():
    categories = Category.query.all()
    return render_template('index.html', categories=categories, current_user=current_user)


@app.route('/api/locations')
def api_locations():
    cat = request.args.get('category')
    query = Location.query
    if cat:
        query = query.join(Category).filter(Category.name == cat)
    locations = query.all()

    data = []
    for loc in locations:
        reviews = Review.query.filter_by(location_id=loc.id).all()
        if reviews:
            avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1)
        else:
            avg_rating = 0
        data.append({
            'id': loc.id,
            'name': loc.name,
            'lat': loc.lat,
            'lng': loc.lng,
            'category': loc.category.name if loc.category else '',
            'description': loc.description,
            'address': loc.address,
            'photo': loc.photo,
            'opening_hours': loc.opening_hours,
            'contacts': loc.contacts,
            'avg_rating': avg_rating,
            'reviews_count': len(reviews)
        })
    return jsonify(data)



@app.route('/location/<int:loc_id>')
def location_detail(loc_id):
    loc = Location.query.get_or_404(loc_id)
    reviews = Review.query.filter_by(location_id=loc.id).all()
    is_fav = False
    if current_user.is_authenticated:
        is_fav = Favorite.query.filter_by(user_id=current_user.id, location_id=loc.id).first() is not None
    return render_template('location.html', location=loc, reviews=reviews, is_fav=is_fav)


@app.route('/review/add/<int:loc_id>', methods=['POST'])
@login_required
def add_review(loc_id):
    rating = int(request.form.get('rating'))
    comment = request.form.get('comment')
    review = Review(user_id=current_user.id, location_id=loc_id, rating=rating, comment=comment)
    db.session.add(review)
    db.session.commit()
    return redirect(url_for('location_detail', loc_id=loc_id))

# Декоратор для JSON API вместо редиректа
def login_required_json(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# Добавление в избранное
@app.route('/favorite/<int:loc_id>', methods=['POST'])
@login_required_json
def add_favorite(loc_id):
    fav = Favorite.query.filter_by(user_id=current_user.id, location_id=loc_id).first()
    if fav:
        return jsonify({'status': 'error', 'msg': 'Уже в избранном'}), 400

    new_fav = Favorite(user_id=current_user.id, location_id=loc_id)
    db.session.add(new_fav)
    db.session.commit()
    return jsonify({'status': 'ok', 'action': 'added'})

# Удаление из избранного
@app.route('/favorite/<int:loc_id>', methods=['DELETE'])
@login_required_json
def remove_favorite(loc_id):
    fav = Favorite.query.filter_by(user_id=current_user.id, location_id=loc_id).first()
    if not fav:
        return jsonify({'status': 'error', 'msg': 'Не найдено в избранном'}), 404

    db.session.delete(fav)
    db.session.commit()
    return jsonify({'status': 'ok', 'action': 'removed'})

# отзывы
@app.route('/location/<int:loc_id>/reviews')
def reviews_page(loc_id):
    loc = Location.query.get_or_404(loc_id)
    sort = request.args.get('sort', 'desc')

    query = Review.query.filter_by(location_id=loc.id)
    if sort == 'asc':
        query = query.order_by(Review.rating.asc())
    else:
        query = query.order_by(Review.rating.desc())

    reviews = query.all()
    avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1) if reviews else 0

    return render_template(
        'reviews.html',
        location=loc,
        reviews=reviews,
        avg_rating=avg_rating,
        sort=sort
    )
#удаление отзыва
@app.route('/review/delete/<int:review_id>', methods=['POST'])
@login_required
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)
    if review.user_id != current_user.id and current_user.role != 'admin':
        flash('Вы не можете удалить этот отзыв')
        return redirect(url_for('reviews_page', loc_id=review.location_id))

    db.session.delete(review)
    db.session.commit()
    flash('Отзыв удалён')
    return redirect(url_for('reviews_page', loc_id=review.location_id))



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        flash('Неверный логин или пароль')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('index'))
    return render_template('register.html')


@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_panel():
    if current_user.role != 'admin':
        flash('Нет доступа')
        return redirect(url_for('index'))

    users = User.query.all()
    categories = Category.query.all()
    total_users = User.query.count()
    total_categories = Category.query.count()

    return render_template('admin.html',
                           users=users,
                           categories=categories,
                           total_users=total_users,
                           total_categories=total_categories)

# ===== Пользователи =====
@app.route('/admin/add_user', methods=['POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        return jsonify({'status': 'error', 'msg': 'Нет доступа'}), 403

    username = request.form['username']
    password = generate_password_hash(request.form['password'])
    role = request.form['role']

    if User.query.filter_by(username=username).first():
        return jsonify({'status': 'error', 'msg': 'Пользователь уже существует'}), 400

    db.session.add(User(username=username, password=password, role=role))
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.role != 'admin':
        return jsonify({'status': 'error', 'msg': 'Нет доступа'}), 403
    user = User.query.get_or_404(user_id)
    if user.username == 'admin1':
        return jsonify({'status': 'error', 'msg': 'Нельзя удалить главного админа'}), 400
    db.session.delete(user)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/admin/edit_user/<int:user_id>', methods=['POST'])
@login_required
def edit_user(user_id):
    if current_user.role != 'admin':
        return jsonify({'status': 'error', 'msg': 'Нет доступа'}), 403
    user = User.query.get_or_404(user_id)
    user.role = request.form['role']
    db.session.commit()
    return jsonify({'status': 'ok'})

# ===== Категории =====
@app.route('/admin/add_category', methods=['POST'])
@login_required
def add_category():
    if current_user.role not in ['admin', 'moderator']:
        return jsonify({'status': 'error', 'msg': 'Нет доступа'}), 403
    name = request.form.get('name')
    if not name:
        return jsonify({'status': 'error', 'msg': 'Название обязательно'}), 400
    if Category.query.filter_by(name=name).first():
        return jsonify({'status': 'error', 'msg': 'Категория уже есть'}), 400
    db.session.add(Category(name=name))
    db.session.commit()
    return jsonify({'status': 'ok', 'name': name})

# избранное
# Декоратор для JSON API вместо редиректа
def login_required_json(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated

# Роут избранного с проверкой через JSON-декоратор
@app.route('/api/favorites')
@login_required_json
def api_favorites():
    favs = Favorite.query.filter_by(user_id=current_user.id).all()
    data = []
    for f in favs:
        if not f.location:
            continue  # пропускаем битые записи
        data.append({
            'id': f.location.id,
            'name': f.location.name,
            'lat': f.location.lat,
            'lng': f.location.lng,
            'photo': f.location.photo or '',  # на всякий случай
            'description': f.location.description or '',
        })
    return jsonify(data)




@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/api/add_location', methods=['POST'])
@login_required
def add_location_api():
    if current_user.role not in ['admin', 'moderator']:
        return jsonify({'status': 'error', 'msg': 'Нет доступа'}), 403

    data = request.json
    loc = Location(
        name=data['name'],
        lat=data['lat'],
        lng=data['lng'],
        description=data.get('description', ''),
        category_id=int(data.get('category', 1))
    )
    db.session.add(loc)
    db.session.commit()
    return jsonify({'status': 'ok', 'id': loc.id})

# сохранение своей метки владельцу
@app.route('/api/my_location/add', methods=['POST'])
@login_required_json
def add_my_location():
    data = request.json

    loc = Location(
        name=data['name'],
        lat=data['lat'],
        lng=data['lng'],
        description=data.get('description', ''),
        address=data.get('address', ''),
        photo=data.get('photo', ''),
        opening_hours=data.get('opening_hours', ''),
        contacts=data.get('contacts', ''),
        category_id=int(data.get('category', 1)),
        owner_id=current_user.id  # ← ВАЖНО
    )

    db.session.add(loc)
    db.session.commit()
    return jsonify({'status': 'ok', 'id': loc.id})

# редактирование своей метки
@app.route('/api/my_location/edit/<int:loc_id>', methods=['PUT'])
@login_required_json
def edit_my_location(loc_id):
    loc = Location.query.get_or_404(loc_id)

    # Проверяем право редактирования
    if loc.owner_id != current_user.id and current_user.role not in ['admin', 'moderator']:
        return jsonify({'status': 'error', 'msg': 'Нет прав редактировать эту локацию'}), 403

    data = request.json
    loc.name = data.get('name', loc.name)
    loc.description = data.get('description', loc.description)
    loc.address = data.get('address', loc.address)
    loc.photo = data.get('photo', loc.photo)
    loc.opening_hours = data.get('opening_hours', loc.opening_hours)
    loc.contacts = data.get('contacts', loc.contacts)
    loc.category_id = int(data.get('category', loc.category_id))

    db.session.commit()
    return jsonify({'status': 'ok', 'msg': 'Локация обновлена'})

# удаление своей метки
@app.route('/api/my_location/delete/<int:loc_id>', methods=['DELETE'])
@login_required_json
def delete_my_location(loc_id):
    loc = Location.query.get_or_404(loc_id)

    if loc.owner_id != current_user.id and current_user.role not in ['admin', 'moderator']:
        return jsonify({'status': 'error', 'msg': 'Нет прав удалить эту локацию'}), 403

    db.session.delete(loc)
    db.session.commit()
    return jsonify({'status': 'ok', 'msg': 'Локация удалена'})

# вывод только своей локации в профиле
@app.route('/my_locations')
@login_required
def my_locations():
    locations = Location.query.filter_by(owner_id=current_user.id).all()
    return render_template('my_locations.html', locations=locations)
# переход на редактирование
@app.route('/edit_location/<int:loc_id>', methods=['GET', 'POST'])
@login_required
def edit_location_page(loc_id):
    loc = Location.query.get_or_404(loc_id)

    # Проверяем права: только владелец или админ/модератор
    if loc.owner_id != current_user.id and current_user.role not in ['admin', 'moderator']:
        flash("Нет прав редактировать эту локацию", "error")
        return redirect(url_for('my_locations'))

    if request.method == 'POST':
        loc.name = request.form.get('name', loc.name)
        loc.description = request.form.get('description', loc.description)
        loc.address = request.form.get('address', loc.address)
        loc.photo = request.form.get('photo', loc.photo)
        loc.opening_hours = request.form.get('opening_hours', loc.opening_hours)
        loc.contacts = request.form.get('contacts', loc.contacts)
        loc.category_id = int(request.form.get('category', loc.category_id))
        db.session.commit()
        flash("Локация обновлена ✅", "success")
        return redirect(url_for('my_locations'))

    categories = Category.query.all()  # Для селекта категорий
    return render_template('edit_location.html', loc=loc, categories=categories)



if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # === Создание администратора ===
        if not User.query.filter_by(username='admin1').first():
            admin = User(
                username='admin1',
                password=generate_password_hash('1234'),
                role='admin'
            )
            db.session.add(admin)
            print("✅ Создан админ: admin1 / 1234")

        # === Создание владельца бизнеса ===
        if not User.query.filter_by(username='owner1').first():
            owner = User(
                username='owner1',
                password=generate_password_hash('1234'),
                role='owner'   # можно также назвать 'business', если так в модели
            )
            db.session.add(owner)
            print("✅ Создан владелец: owner1 / 1234")

        db.session.commit()

    app.run(host="0.0.0.0", port=5000, debug=True)

