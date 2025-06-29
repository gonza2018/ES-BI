from flask import Flask, render_template, send_from_directory
from flask_compress import Compress
import os


app = Flask(__name__)
Compress(app)


@app.route('/')
def index():
    return render_template("index.html")


@app.route('/contacto')
def contacto():
    return render_template("contact.html")


@app.route('/send_mail')
def send_mail():
    return render_template("send_mail.html")


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )


@app.after_request
def add_header(response):
    if 'Cache-Control' not in response.headers and (
        response.content_type.startswith('text/') or
        'javascript' in response.content_type or
        'image' in response.content_type
    ):
        response.cache_control.max_age = 31536000  # 1 año en segundos
        response.cache_control.public = True
    return response


if __name__ == '__main__':
    app.run(debug=True)
