# 必要なライブラリとモジュールのインポート
import os # ファイル操作のためのOSモジュール
from datetime import date, datetime, timedelta # 日付と時間の操作
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify # Flaskフレームワークの主要コンポーネント
from flask_sqlalchemy import SQLAlchemy # FlaskでSQLAlchemyを使用するための拡張
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user # ユーザー認証機能
from werkzeug.security import generate_password_hash, check_password_hash # パスワードのハッシュ化
from werkzeug.utils import secure_filename # アップロードされたファイル名の安全化
from flask_wtf import FlaskForm # FlaskでWTFormsを使用するための拡張
from wtforms import StringField, SelectField, SubmitField, URLField # フォームのフィールドタイプ
from wtforms.validators import DataRequired, URL, Length # フォームのバリデーター
from flask_migrate import Migrate # データベースマイグレーション
import requests # HTTP リクエスト
from apscheduler.schedulers.background import BackgroundScheduler  # バックグラウンドタスクのスケジューリング
from apscheduler.triggers.cron import CronTrigger # クーロン式でのスケジュール設定

# Flaskアプリケーションの初期化
app = Flask(__name__)
# アプリケーションの設定
app.config['SECRET_KEY'] = 'your-secret-key' # セッションの暗号化に使用する秘密鍵
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///music_sns.db' # SQLiteデータベースの場所
app.config['UPLOAD_FOLDER'] = 'static/uploads' # アップロードされたファイルの保存先
app.config['ALLOWED_EXTENSIONS'] = {'mp3', 'wav', 'ogg'} # 許可するファイル拡張子

# データベースの初期化
db = SQLAlchemy(app)
# データベースマイグレーションの設定
migrate = Migrate(app, db)
# ログイン管理の初期化
login_manager = LoginManager(app)
login_manager.login_view = 'login'# ログインページのビュー名を指定

# フォロワーの関連テーブルの定義
followers = db.Table('followers',
                     db.Column('follower_id', db.Integer,
                               db.ForeignKey('user.id')), # フォローしているユーザーのID
                     db.Column('followed_id', db.Integer,
                               db.ForeignKey('user.id')) # フォローされているユーザーのID
                     )

# ユーザーモデルの定義
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True) # ユーザーの一意のID
    username = db.Column(db.String(80), unique=True, nullable=False) # ユーザー名（一意）
    password = db.Column(db.String(120), nullable=False) # パスワード（ハッシュ化して保存）
    favorite_band = db.Column(db.String(120)) # お気に入りのバンド
    favorite_genre = db.Column(db.String(50)) # お気に入りのジャンル
    icon = db.Column(db.String(120)) # ユーザーアイコンのファイルパス

    # フォロー関係の定義
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

    # ユーザーをフォローするメソッド
    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)
    # ユーザーのフォローを解除するメソッド
    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)
    # ユーザーをフォローしているかチェックするメソッド
    def is_following(self, user):
        return self.followed.filter(
            followers.c.followed_id == user.id).count() > 0

# 日々の楽曲投稿モデルの定義
class DailySong(db.Model):
    id = db.Column(db.Integer, primary_key=True) # 投稿の一意のID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # 投稿したユーザーのID
    title = db.Column(db.String(100), nullable=False) # 曲のタイトル
    artist = db.Column(db.String(100), nullable=False) # アーティスト名
    genre = db.Column(db.String(50), nullable=False) # ジャンル
    music_url = db.Column(db.String(500), nullable=False) # 音楽の共有URL
    date_posted = db.Column(db.Date, nullable=False, default=date.today) # 投稿日
    is_current = db.Column(db.Boolean, default=True) # 現在の投稿かどうか

    # ユーザーとの関係を定義
    user = db.relationship(
        'User', backref=db.backref('daily_songs', lazy=True))

# 日々の楽曲投稿フォームの定義
class DailySongForm(FlaskForm):
    title = StringField('曲のタイトル', validators=[DataRequired()]) # 曲のタイトル入力フィールド
    artist = StringField('アーティスト名', validators=[DataRequired()]) # アーティスト名入力フィールド
    genre = SelectField('ジャンル', choices=[
        ('pop', 'J-POP'),
        ('rock', 'K-POP'),
        ('jazz', 'ヒップホップ/ラップ'),
        ('classical', 'ロック'),
        ('hiphop', 'ジャズ'),
        ('electronic', 'クラシック'),
        ('other', 'その他')
    ], validators=[DataRequired()])  # ジャンル選択フィールド
    music_url = URLField('音楽の共有URL', validators=[DataRequired(), URL()]) # 音楽URLの入力フィールド
    submit = SubmitField('投稿') # 投稿ボタン

# メッセージフォームの定義
class MessageForm(FlaskForm):
    message = StringField('メッセージ', validators=[
                          DataRequired(), Length(min=1, max=500)]) # メッセージ入力フィールド
    submit = SubmitField('送信') # 送信ボタン

# ユーザーローダーの定義（Flask-Loginで使用）
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# アップロードされたファイルの拡張子をチェックする関数
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ルート（トップページ）
@app.route('/')
def index():
    return render_template('index.html')

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username') # フォームからユーザー名を取得
        password = request.form.get('password') # フォームからパスワードを取得
        user = User.query.filter_by(username=username).first() # ユーザーをデータベースから検索
        if user and check_password_hash(user.password, password): # パスワードが正しいかチェック
            login_user(user) # ユーザーをログイン状態にする
            return redirect(url_for('mypage'))  # マイページにリダイレクト
        flash('Invalid username or password') # エラーメッセージを表示
    return render_template('login.html') # ログインページを表示

# 新規登録ページ
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')  # フォームからユーザー名を取得
        password = request.form.get('password') # フォームからパスワードを取得
        if User.query.filter_by(username=username).first(): # ユーザー名が既に存在するかチェック
            flash('Username already exists') # エラーメッセージを表示

        else:
            new_user = User(username=username,
                            password=generate_password_hash(password))  # 新しいユーザーを作成
            db.session.add(new_user) # データベースに新しいユーザーを追加
            db.session.commit() # 変更を保存
            flash('Registration successful') # 成功メッセージを表示
            return redirect(url_for('login'))  # ログインページにリダイレクト
    return render_template('register.html') # 登録ページを表示


# マイページ
@app.route('/mypage')
@login_required # ログインしているユーザーのみアクセス可能
def mypage():
    today = date.today() # 今日の日付を取得
    daily_song = DailySong.query.filter_by(
        user_id=current_user.id, date_posted=today, is_current=True).first() # 今日の投稿を取得
    past_posts = DailySong.query.filter_by(user_id=current_user.id).order_by(
        DailySong.date_posted.desc()).limit(20).all() # 過去20件の投稿を取得
    return render_template('mypage.html', user=current_user, daily_song=daily_song, past_posts=past_posts) # マイページを表示

# ログアウト
@app.route('/logout')
@login_required # ログインしているユーザーのみアクセス可能
def logout():
    logout_user() # ユーザーをログアウト状態にする
    return redirect(url_for('index')) # トップページにリダイレクト

# ファイルアップロード
@app.route('/upload', methods=['GET', 'POST'])
@login_required # ログインしているユーザーのみアクセス可能
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files: # ファイルがアップロードされているかチェック
            flash('ファイルがありません')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '': # ファイル名が空でないかチェック
            flash('ファイルが選択されていません')
            return redirect(request.url)
        if file and allowed_file(file.filename): # ファイルの拡張子が許可されているかチェック
            filename = secure_filename(file.filename) # ファイル名を安全なものに変換
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename)) # ファイルを保存
            flash('ファイルがアップロードされました')
            return redirect(url_for('mypage')) # マイページにリダイレクト
    return render_template('upload.html') # アップロードページを表示

# 日々の楽曲投稿
@app.route('/post_daily_song', methods=['GET', 'POST'])
@login_required # ログインしているユーザーのみアクセス可能
def post_daily_song():
    form = DailySongForm() # 楽曲投稿フォームを作成
    if form.validate_on_submit(): # フォームのバリデーションが成功した場合
        today = date.today() # 今日の日付を取得
        DailySong.query.filter_by(
            user_id=current_user.id, date_posted=today, is_current=True).update({'is_current': False}) # 以前の投稿を非アクティブにする
        new_song = DailySong(
            user_id=current_user.id,
            title=form.title.data,
            artist=form.artist.data,
            genre=form.genre.data,
            music_url=form.music_url.data,
            is_current=True
        ) # 新しい楽曲投稿を作成
        db.session.add(new_song) # データベースに新しい投稿を追加
        db.session.commit() # 変更を保存
        flash('今日の1曲を投稿しました!', 'success') # 成功メッセージを表示
        return redirect(url_for('mypage')) # マイページにリダイレクト
    return render_template('post_daily_song.html', form=form) # 投稿ページを表示

# すべての投稿を表示
@app.route('/all_posts')
def all_posts():
    sort_order = request.args.get('sort', 'desc') # ソート順を取得（デフォルトは降順）
    if sort_order == 'asc':
        posts = DailySong.query.order_by(DailySong.date_posted.asc()).all() # 投稿を昇順で取得
    else:
        posts = DailySong.query.order_by(DailySong.date_posted.desc()).all()  # 投稿を降順で取得

    followed_posts = []
    if current_user.is_authenticated: # ユーザーがログインしている場合
        followed_users = [user.id for user in current_user.followed] # フォローしているユーザーのIDリストを取得
        if sort_order == 'asc':
            followed_posts = DailySong.query.filter(DailySong.user_id.in_(
                followed_users)).order_by(DailySong.date_posted.asc()).all() # フォローしているユーザーの投稿を昇順で取得
        else:
            followed_posts = DailySong.query.filter(DailySong.user_id.in_(
                followed_users)).order_by(DailySong.date_posted.desc()).all() # フォローしているユーザーの投稿を降順で取得

    return render_template('all_posts.html', posts=posts, followed_posts=followed_posts, current_sort=sort_order) # 全ての投稿ページを表示

# ユーザーをフォロー
@app.route('/follow/<username>')
@login_required # ログインしているユーザーのみアクセス可能
def follow(username):
    user = User.query.filter_by(username=username).first() # フォローするユーザーを取得
    if user is None:
        flash('ユーザーが見つかりません。')
        return redirect(url_for('index')) # ユーザーが存在しない場合、トップページにリダイレクト
    if user == current_user:
        flash('自分自身をフォローすることはできません。')
        return redirect(url_for('user', username=username)) # 自分自身をフォローしようとした場合、プロフィールページにリダイレクト
    current_user.follow(user) # ユーザーをフォロー
    db.session.commit() # 変更を保存
    flash(f'{username} をフォローしました。')
    return redirect(url_for('user', username=username)) # フォローしたユーザーのプロフィールページにリダイレクト

# ユーザーのフォローを解除
@app.route('/unfollow/<username>')
@login_required # ログインしているユーザーのみアクセス可能
def unfollow(username):
    user = User.query.filter_by(username=username).first() # フォロー解除するユーザーを取得
    if user is None:
        flash('ユーザーが見つかりません。')
        return redirect(url_for('index')) # ユーザーが存在しない場合、トップページにリダイレクト 
    if user == current_user:
        flash('自分自身をアンフォローすることはできません。')
        return redirect(url_for('user', username=username)) # 自分自身をアンフォローしようとした場合、プロフィールページにリダイレクト
    current_user.unfollow(user) # ユーザーのフォローを解除
    db.session.commit() # 変更を保存
    flash(f'{username} のフォローを解除しました。')
    return redirect(url_for('user', username=username)) # フォロー解除したユーザーのプロフィールページにリダイレクト

# ユーザープロフィールページ
@app.route('/user/<username>')
@login_required # ログインしているユーザーのみアクセス可能
def user(username):
    user = User.query.filter_by(username=username).first_or_404() # ユーザーを取得、存在しない場合は404エラー
    posts = DailySong.query.filter_by(user_id=user.id).order_by(
        DailySong.date_posted.desc()).all() # ユーザーの投稿を降順で取得
    return render_template('user.html', user=user, posts=posts) # ユーザープロフィールページを表示

# メッセージ送信
@app.route('/send_message/<recipient>', methods=['GET', 'POST'])
@login_required # ログインしているユーザーのみアクセス可能
def send_message(recipient):
    user = User.query.filter_by(username=recipient).first_or_404() # 受信者を取得、存在しない場合は404エラー
    form = MessageForm()  # メッセージフォームを作成
    if form.validate_on_submit(): # フォームのバリデーションが成功した場合
        msg = Message(sender=current_user, recipient=user,
                      body=form.message.data) # 新しいメッセージを作成
        db.session.add(msg) # データベースにメッセージを追加
        db.session.commit() # 変更を保存
        flash('メッセージを送信しました。')
        return redirect(url_for('user', username=recipient)) # 受信者のプロフィールページにリダイレクト
    return render_template('send_message.html', title='メッセージ送信', form=form, recipient=recipient) # メッセージ送信ページを表示

# Spotify APIを使用してアルバムアートを取得
def get_album_art(artist, title):
    client_id = 'your_spotify_client_id' # Spotify API クライアントID
    client_secret = 'your_spotify_client_secret' # Spotify API クライアントシークレット

    auth_response = requests.post('https://accounts.spotify.com/api/token', {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
    }) # Spotify APIの認証トークンを取得
    auth_response_data = auth_response.json()
    access_token = auth_response_data['access_token']

    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    params = {
        'q': f'artist:{artist} track:{title}',
        'type': 'track',
        'limit': 1
    }
    response = requests.get(
        'https://api.spotify.com/v1/search', headers=headers, params=params) # Spotify APIで楽曲を検索
    response_data = response.json()

    if 'tracks' in response_data and response_data['tracks']['items']:
        return response_data['tracks']['items'][0]['album']['images'][0]['url'] # アルバムアートのURLを返す
    else:
        return None # アルバムアートが見つからない場合はNoneを返す

# アルバムアートを取得するAPIエンドポイント
@app.route('/get_album_art/<artist>/<title>')
def get_album_art_api(artist, title):
    album_art_url = get_album_art(artist, title) # アルバムアートのURLを取得
    return jsonify({'album_art_url': album_art_url}) # JSONレスポンスを返す

# 日々の楽曲をリセットする関数
def reset_daily_songs():
    with app.app_context(): # アプリケーションコンテキストを使用
        yesterday = date.today() - timedelta(days=1) # 昨日の日付を取得
        DailySong.query.filter(DailySong.date_posted <=
                               yesterday).update({'is_current': False}) # 昨日以前の投稿を非アクティブにする
        db.session.commit() # 変更を保存
        print(f"Daily songs reset at {datetime.now()}") # リセット完了のログを出力

# バックグラウンドジョブのスケジューラー設定
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=reset_daily_songs,
    trigger=CronTrigger(hour=4, minute=0), # 毎日午前4時に実行
    id='reset_daily_songs_job',
    name='Reset daily songs every day at 4 AM',
    replace_existing=True)
scheduler.start()  # スケジューラーを開始

# メインの実行部分
if __name__ == '__main__':
    with app.app_context():
        db.create_all() # データベースのテーブルを作成
    app.run(debug=True) # デバッグモードでアプリケーションを実行