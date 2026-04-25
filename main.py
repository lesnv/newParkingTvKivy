import os
import json
import requests
import threading
from datetime import datetime, timedelta, timezone
from queue import Queue, Empty

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.filechooser import FileChooserListView
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.core.image import Image as CoreImage
from kivy.utils import platform

CONFIG_FILE = 'settings.json'
DEFAULT_API_URL = "https://ucams.ufanet.ru"
DEFAULT_USER = ""
DEFAULT_PASS = ""
DEFAULT_INTERVAL = 5
DEFAULT_CAMERAS = []
DEFAULT_FONT_SIZE = 150
DEFAULT_BG_COLOR = "000000"
DEFAULT_TEXT_COLOR = "FFFFFF"
DEFAULT_BG_IMAGE = ""

COLOR_PRESETS = [
    ("000000", "Чёрный"), ("FFFFFF", "Белый"), ("FF0000", "Красный"),
    ("00FF00", "Зелёный"), ("0000FF", "Синий"), ("FFFF00", "Жёлтый"),
    ("00FFFF", "Голубой"), ("FF00FF", "Пурпурный"), ("808080", "Серый"),
    ("800000", "Бордо"), ("008000", "Тёмно-зелёный"), ("000080", "Тёмно-синий"),
    ("FFA500", "Оранжевый"), ("FFC0CB", "Розовый"), ("A52A2A", "Коричневый"),
    ("C0C0C0", "Серебро"), ("FFD700", "Золото")
]


class SettingsManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.config = {
            'api_url': DEFAULT_API_URL, 'user': DEFAULT_USER, 'pass': DEFAULT_PASS,
            'interval': DEFAULT_INTERVAL, 'cameras': DEFAULT_CAMERAS,
            'font_size': DEFAULT_FONT_SIZE, 'bg_color': DEFAULT_BG_COLOR,
            'text_color': DEFAULT_TEXT_COLOR, 'bg_image': DEFAULT_BG_IMAGE
        }
        self.load_config()

    def load_config(self):
        with self._lock:
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                        for key in self.config:
                            if key in loaded:
                                self.config[key] = loaded[key]
                except Exception as e:
                    print(f"Ошибка загрузки: {e}")

    def save_config(self):
        with self._lock:
            try:
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                print(f"Ошибка сохранения: {e}")
                return False

    def get(self, key, default=None):
        with self._lock:
            return self.config.get(key, default)

    def set(self, key, value):
        with self._lock:
            self.config[key] = value


settings = SettingsManager()


def hex_to_rgba(hex_color, alpha=1.0):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return [0, 0, 0, alpha]
    try:
        return [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [alpha]
    except ValueError:
        return [0, 0, 0, alpha]


class ColorPickerPopup(Popup):
    def __init__(self, on_select, **kwargs):
        super().__init__(**kwargs)
        self.on_select = on_select
        self.title = "Выберите цвет"
        self.size_hint = (0.95, 0.8)
        layout = BoxLayout(orientation='vertical', spacing=10, padding=15)
        grid = GridLayout(cols=4, spacing=8, size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        for hex_val, name in COLOR_PRESETS:
            btn = Button(text="", background_color=hex_to_rgba(hex_val),
                         background_normal='', size_hint_y=None, height=60)
            btn.bind(on_release=lambda btn, h=hex_val: self._select(h))
            grid.add_widget(btn)
        scroll = ScrollView()
        scroll.add_widget(grid)
        layout.add_widget(scroll)
        btn_cancel = Button(text="Отмена", size_hint_y=None, height=45, font_size='16sp')
        btn_cancel.bind(on_release=self.dismiss)
        layout.add_widget(btn_cancel)
        self.content = layout

    def _select(self, hex_val):
        if self.on_select:
            self.on_select(hex_val)
        self.dismiss()


class ApiClient:
    def __init__(self):
        self._token = None
        self._token_lock = threading.Lock()

    def _request_new_token(self):
        try:
            # === УЛУЧШЕНИЕ: безопасное получение URL ===
            base_url = (settings.get('api_url') or DEFAULT_API_URL).strip()
            if not base_url:
                base_url = DEFAULT_API_URL
            auth_url = f"{base_url}/api/v0/auth/"
            auth_data = {"username": settings.get('user', ''), "password": settings.get('pass', '')}
            resp = requests.post(auth_url, json=auth_data, verify=False, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                token = data.get('access_token') or data.get('token') or data.get('access')
                if token:
                    print("✓ Токен получен")
                    return token
            print(f"✗ Ошибка авторизации: {resp.status_code}")
            return None
        except Exception as e:
            print(f"✗ Ошибка получения токена: {e}")
            return None

    def get_token(self, force_refresh=False):
        with self._token_lock:
            if not self._token or force_refresh:
                self._token = self._request_new_token()
            return self._token

    def make_request(self, url, payload):
        token = self.get_token()
        if not token:
            return None, "Ошибка авторизации"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        try:
            resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            if resp.status_code == 200:
                return resp.json(), None
            elif resp.status_code == 401:
                new_token = self.get_token(force_refresh=True)
                if new_token:
                    headers['Authorization'] = f'Bearer {new_token}'
                    resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
                    if resp.status_code == 200:
                        return resp.json(), None
                return None, "Ошибка авторизации (401)"
            else:
                return None, f"Ошибка API: {resp.status_code}"
        except Exception as e:
            return None, f"Сетевая ошибка: {e}"


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_client = ApiClient()
        self.update_scheduled = None
        self._current_camera_idx = 0
        self._bg_color_instr = None
        self._bg_rect = None
        self._bg_initialized = False

        self.lbl_header = Label(text="", font_size='40sp', bold=True,
                                color=hex_to_rgba(settings.get('text_color', DEFAULT_TEXT_COLOR)),
                                halign='center', valign='middle', size_hint_y=None, height=50)
        self.lbl_count = Label(text="...",
                               font_size=f"{settings.get('font_size', DEFAULT_FONT_SIZE)}sp", bold=True,
                               color=hex_to_rgba(settings.get('text_color', DEFAULT_TEXT_COLOR)),
                               halign='center', valign='middle')
        self.lbl_status = Label(text="Загрузка...", font_size='20sp',
                                color=hex_to_rgba(settings.get('text_color', DEFAULT_TEXT_COLOR)),
                                size_hint_y=None, height=35)

        nav_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        self.btn_prev_camera = Button(text="◀", font_size='20sp', size_hint_x=None, width=60)
        self.btn_next_camera = Button(text="▶", font_size='20sp', size_hint_x=None, width=60)
        self.lbl_camera_info = Label(text="Камера 1/1", font_size='16sp',
                                     color=hex_to_rgba(settings.get('text_color', DEFAULT_TEXT_COLOR)))
        self.btn_prev_camera.bind(on_release=self.prev_camera)
        self.btn_next_camera.bind(on_release=self.next_camera)
        nav_layout.add_widget(self.btn_prev_camera)
        nav_layout.add_widget(self.lbl_camera_info)
        nav_layout.add_widget(self.btn_next_camera)

        self.btn_settings = Button(text="⚙ Настройки", size_hint_y=None, height=50, font_size='20sp')
        self.btn_settings.bind(on_release=self.go_to_settings)

        layout = BoxLayout(orientation='vertical', padding=15, spacing=15)
        layout.add_widget(self.lbl_header)
        layout.add_widget(self.lbl_count)
        layout.add_widget(self.lbl_status)
        layout.add_widget(nav_layout)
        layout.add_widget(self.btn_settings)
        self.add_widget(layout)

        Clock.schedule_once(self._init_canvas_background, 0)

        self._ui_queue = Queue()
        Clock.schedule_interval(self._process_ui_queue, 0.1)

    def _init_canvas_background(self, *args):
        if self._bg_initialized:
            return
        self._bg_initialized = True
        with self.canvas.before:
            self._bg_color_instr = Color(*hex_to_rgba(settings.get('bg_color', DEFAULT_BG_COLOR)))
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg_rect, size=self._update_bg_rect)
        self._apply_bg_settings()

    def _update_bg_rect(self, *args):
        if self._bg_initialized and self._bg_rect:
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size

    def _apply_bg_settings(self):
        if not self._bg_initialized or not self._bg_color_instr or not self._bg_rect:
            return
        bg_color = settings.get('bg_color', DEFAULT_BG_COLOR)
        bg_image = settings.get('bg_image', '').strip()
        self._bg_color_instr.rgba = hex_to_rgba(bg_color)
        if bg_image and os.path.exists(bg_image):
            try:
                self._bg_rect.texture = CoreImage(bg_image).texture
            except:
                self._bg_rect.texture = None
        else:
            self._bg_rect.texture = None

    def _process_ui_queue(self, dt):
        try:
            while True:
                func, args = self._ui_queue.get_nowait()
                func(*args)
        except Empty:
            pass

    def _schedule_ui_update(self, func, *args):
        self._ui_queue.put((func, args))

    def on_enter(self, *args):
        if self._bg_initialized:
            self._apply_bg_settings()
        else:
            Clock.schedule_once(lambda dt: self._apply_bg_settings(), 0.05)
        self._update_camera_info()
        self._start_polling()

    def on_leave(self, *args):
        self._stop_polling()

    def _start_polling(self):
        self._stop_polling()
        self._fetch_and_schedule()

    def _stop_polling(self):
        if self.update_scheduled:
            self.update_scheduled.cancel()
            self.update_scheduled = None

    def _fetch_and_schedule(self, dt=None):
        threading.Thread(target=self._fetch_data, daemon=True).start()
        interval = max(1, settings.get('interval', DEFAULT_INTERVAL))
        self.update_scheduled = Clock.schedule_once(self._fetch_and_schedule, interval)

    def _fetch_data(self):
        cameras = settings.get('cameras', [])
        if not cameras:
            self._schedule_ui_update(self._set_status, "Добавьте камеру в настройках")
            return
        if self._current_camera_idx >= len(cameras):
            self._current_camera_idx = 0
        camera = cameras[self._current_camera_idx]
        camera_number = camera.get('number', '').strip()
        header = camera.get('header', '').strip()
        if not camera_number:
            self._schedule_ui_update(self._set_status, "Укажите номер камеры")
            return
        self._schedule_ui_update(setattr, self.lbl_header, 'text', header)
        # === УЛУЧШЕНИЕ: безопасное получение URL ===
        api_url = (settings.get('api_url') or DEFAULT_API_URL).strip()
        if not api_url:
            api_url = DEFAULT_API_URL
        report_url = f"{api_url}/api/v0/analytics/parking_detection/report/"
        now = datetime.now(timezone.utc)
        payload = {
            "page": 1, "page_size": 1,
            "start": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "query": "", "ordering": [{"sort": "id", "order": "DESC"}],
            "camera_number": camera_number
        }
        data, error = self.api_client.make_request(report_url, payload)
        if error:
            self._schedule_ui_update(self._set_status, error)
            return
        display_text = self._parse_response(data)
        if display_text is not None:
            now_str = datetime.now().strftime("%H:%M:%S")
            self._schedule_ui_update(self._update_ui, str(display_text), now_str)
        else:
            self._schedule_ui_update(self._set_status, "Нет данных")

    def _parse_response(self, data):
        if isinstance(data, dict):
            if "text" in data:
                return data["text"]
            if "results" in data and data["results"]:
                first = data["results"][0]
                if isinstance(first, dict) and "text" in first:
                    return first["text"]
                if isinstance(first, (int, float, str)):
                    return str(first)
            if "count" in data:
                return data["count"]
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    return str(value)
        elif isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and "text" in first:
                return first["text"]
            if isinstance(first, (int, float, str)):
                return str(first)
        return None

    def _set_status(self, text):
        self.lbl_status.text = text

    def _update_ui(self, display_text, timestamp):
        self.lbl_count.text = str(display_text)
        self.lbl_status.text = f"Обновлено: {timestamp}"

    def prev_camera(self, instance):
        cameras = settings.get('cameras', [])
        if cameras:
            self._current_camera_idx = (self._current_camera_idx - 1) % len(cameras)
            self._update_camera_info()

    def next_camera(self, instance):
        cameras = settings.get('cameras', [])
        if cameras:
            self._current_camera_idx = (self._current_camera_idx + 1) % len(cameras)
            self._update_camera_info()

    def _update_camera_info(self):
        cameras = settings.get('cameras', [])
        if cameras and self._current_camera_idx < len(cameras):
            cam = cameras[self._current_camera_idx]
            name = cam.get('name', cam.get('number', '?'))
            self.lbl_camera_info.text = f"{name} ({self._current_camera_idx + 1}/{len(cameras)})"
        else:
            self.lbl_camera_info.text = "Нет камер"

    def go_to_settings(self, instance):
        self.manager.current = 'settings'


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.camera_rows = []
        self._content = None
        self.build_ui()

    def build_ui(self):
        self.clear_widgets()
        self.camera_rows = []
        scroll = ScrollView(size_hint=(1, 1))
        self._content = BoxLayout(orientation='vertical', padding=15, spacing=10, size_hint_y=None)
        self._content.bind(minimum_height=self._content.setter('height'))

        self._content.add_widget(Label(text="🔐 Авторизация", size_hint_y=None, height=35, bold=True, font_size='16sp'))
        self.input_url = TextInput(hint_text="URL API", text=settings.get('api_url', ''), multiline=False,
                                   font_size='14sp', size_hint_y=None, height=40)
        self.input_user = TextInput(hint_text="Логин", text=settings.get('user', ''), multiline=False, font_size='14sp',
                                    size_hint_y=None, height=40)
        self.input_pass = TextInput(hint_text="Пароль", text=settings.get('pass', ''), password=True, multiline=False,
                                    font_size='14sp', size_hint_y=None, height=40)
        self._content.add_widget(self.input_url)
        self._content.add_widget(self.input_user)
        self._content.add_widget(self.input_pass)

        self._content.add_widget(Label(text="📷 Камеры", size_hint_y=None, height=35, bold=True, font_size='16sp'))
        self.camera_container = BoxLayout(orientation='vertical', spacing=8, size_hint_y=None, padding=(0, 5))
        self.camera_container.bind(minimum_height=self.camera_container.setter('height'))
        self._content.add_widget(self.camera_container)
        btn_add = Button(text="+ Добавить камеру", size_hint_y=None, height=45, font_size='16sp')
        btn_add.bind(on_release=self.add_camera_row)
        self._content.add_widget(btn_add)

        self._content.add_widget(Label(text="⚙ Общие", size_hint_y=None, height=35, bold=True, font_size='16sp'))
        self.input_interval = TextInput(hint_text="Интервал (сек)",
                                        text=str(settings.get('interval', DEFAULT_INTERVAL)), input_filter='int',
                                        multiline=False, font_size='14sp', size_hint_y=None, height=40)
        self.input_font = TextInput(hint_text="Размер шрифта", text=str(settings.get('font_size', DEFAULT_FONT_SIZE)),
                                    input_filter='int', multiline=False, font_size='14sp', size_hint_y=None, height=40)
        self._content.add_widget(self.input_interval)
        self._content.add_widget(self.input_font)

        self._content.add_widget(Label(text="🎨 Цвета", size_hint_y=None, height=35, bold=True, font_size='16sp'))
        bg_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
        self.input_bg = TextInput(hint_text="Цвет фона (hex)", text=settings.get('bg_color', DEFAULT_BG_COLOR),
                                  readonly=True, multiline=False, font_size='14sp')
        self.btn_bg = Button(text="", background_color=hex_to_rgba(settings.get('bg_color', DEFAULT_BG_COLOR)),
                             size_hint_x=None, width=50, background_normal='')
        self.btn_bg.bind(on_release=lambda b: self.open_color_picker('bg'))
        bg_row.add_widget(self.input_bg)
        bg_row.add_widget(self.btn_bg)
        text_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
        self.input_text = TextInput(hint_text="Цвет текста (hex)", text=settings.get('text_color', DEFAULT_TEXT_COLOR),
                                    readonly=True, multiline=False, font_size='14sp')
        self.btn_text = Button(text="", background_color=hex_to_rgba(settings.get('text_color', DEFAULT_TEXT_COLOR)),
                               size_hint_x=None, width=50, background_normal='')
        self.btn_text.bind(on_release=lambda b: self.open_color_picker('text'))
        text_row.add_widget(self.input_text)
        text_row.add_widget(self.btn_text)
        self._content.add_widget(bg_row)
        self._content.add_widget(text_row)

        self._content.add_widget(
            Label(text="🖼️ Фоновое изображение", size_hint_y=None, height=35, bold=True, font_size='16sp'))
        self.input_bgimg = TextInput(hint_text="Путь к изображению", text=settings.get('bg_image', ''), readonly=True,
                                     multiline=False, font_size='14sp', size_hint_y=None, height=40)
        btn_pick = Button(text="📁 Выбрать файл", size_hint_y=None, height=45, font_size='14sp')
        btn_pick.bind(on_release=self.select_image)
        self._content.add_widget(self.input_bgimg)
        self._content.add_widget(btn_pick)

        self._content.add_widget(Label(size_hint_y=None, height=20))
        btn_layout = BoxLayout(size_hint_y=None, height=60, spacing=10, padding=(0, 10, 0, 0))
        btn_save = Button(text="💾 Сохранить", font_size='18sp')
        btn_save.bind(on_release=self.save_settings)
        btn_back = Button(text="⬅ Назад", font_size='18sp')
        btn_back.bind(on_release=self.go_back)
        btn_layout.add_widget(btn_save)
        btn_layout.add_widget(btn_back)
        self._content.add_widget(btn_layout)
        self.lbl_msg = Label(text="", color=(1, 0.5, 0.5, 1), size_hint_y=None, height=30)
        self._content.add_widget(self.lbl_msg)

        scroll.add_widget(self._content)
        self.add_widget(scroll)

        for cam in settings.get('cameras', []):
            self.add_camera_row(None, cam.get('number', ''), cam.get('name', ''), cam.get('header', ''))

    def on_enter(self, *args):
        """Обновление полей актуальными настройками при входе"""
        # === УЛУЧШЕНИЕ: защита от None значений ===
        self.input_url.text = settings.get('api_url', DEFAULT_API_URL) or DEFAULT_API_URL
        self.input_user.text = settings.get('user', DEFAULT_USER) or DEFAULT_USER
        self.input_pass.text = settings.get('pass', DEFAULT_PASS) or DEFAULT_PASS
        self.input_interval.text = str(settings.get('interval', DEFAULT_INTERVAL) or DEFAULT_INTERVAL)
        self.input_font.text = str(settings.get('font_size', DEFAULT_FONT_SIZE) or DEFAULT_FONT_SIZE)
        self.input_bg.text = settings.get('bg_color', DEFAULT_BG_COLOR) or DEFAULT_BG_COLOR
        self.input_text.text = settings.get('text_color', DEFAULT_TEXT_COLOR) or DEFAULT_TEXT_COLOR
        self.input_bgimg.text = settings.get('bg_image', DEFAULT_BG_IMAGE) or DEFAULT_BG_IMAGE
        self.btn_bg.background_color = hex_to_rgba(settings.get('bg_color', DEFAULT_BG_COLOR))
        self.btn_text.background_color = hex_to_rgba(settings.get('text_color', DEFAULT_TEXT_COLOR))

        self.camera_container.clear_widgets()
        self.camera_rows.clear()
        for cam in settings.get('cameras', []):
            self.add_camera_row(None, cam.get('number', ''), cam.get('name', ''), cam.get('header', ''))

    def add_camera_row(self, instance, number='', name='', header=''):
        row = BoxLayout(orientation='vertical', size_hint_y=None, height=140, spacing=5, padding=(0, 5))
        top = BoxLayout(size_hint_y=None, height=40, spacing=5)
        inp_num = TextInput(hint_text="Номер камеры *", text=number, multiline=False, font_size='14sp',
                            size_hint_y=None, height=40)
        inp_name = TextInput(hint_text="Название", text=name, multiline=False, font_size='14sp', size_hint_y=None,
                             height=40)
        top.add_widget(inp_num)
        top.add_widget(inp_name)
        mid = BoxLayout(size_hint_y=None, height=40, spacing=5)
        inp_hdr = TextInput(hint_text="Заголовок", text=header, multiline=False, font_size='14sp', size_hint_y=None,
                            height=40)
        mid.add_widget(inp_hdr)
        bottom = BoxLayout(size_hint_y=None, height=40, spacing=5)
        btn_del = Button(text="✕ Удалить", size_hint_x=None, width=100, font_size='14sp',
                         background_color=(1, 0.3, 0.3, 1))
        btn_del.bind(on_release=lambda b, r=row: self.remove_camera_row(r))
        bottom.add_widget(btn_del)
        row.add_widget(top)
        row.add_widget(mid)
        row.add_widget(bottom)
        self.camera_container.add_widget(row)
        self.camera_rows.append((inp_num, inp_name, inp_hdr, row))

    def remove_camera_row(self, row_widget):
        if row_widget in self.camera_container.children:
            self.camera_container.remove_widget(row_widget)
        self.camera_rows = [(num, name, hdr, row) for num, name, hdr, row in self.camera_rows if row != row_widget]

    def open_color_picker(self, target):
        def on_select(hex_val):
            if target == 'bg':
                self.input_bg.text = hex_val
                self.btn_bg.background_color = hex_to_rgba(hex_val)
            else:
                self.input_text.text = hex_val
                self.btn_text.background_color = hex_to_rgba(hex_val)

        ColorPickerPopup(on_select).open()

    def select_image(self, instance):
        if platform == 'android':
            possible_paths = ['/storage/emulated/0/', '/sdcard/', '/storage/self/primary/', '/']
            start_path = '/'
            for p in possible_paths:
                if os.path.isdir(p):
                    start_path = p
                    break
        else:
            start_path = os.path.expanduser('~')
        content = BoxLayout(orientation='vertical')
        try:
            fc = FileChooserListView(path=start_path, filters=['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif'],
                                     filter_dirs=True)
        except:
            fc = FileChooserListView(path='/', filters=['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif'], filter_dirs=True)
        btns = BoxLayout(size_hint_y=None, height=50, spacing=10)
        btn_ok = Button(text="Выбрать")
        btn_cancel = Button(text="Отмена")
        popup = Popup(title="Выберите изображение", content=content, size_hint=(0.95, 0.85))

        def on_ok(b):
            if fc.selection:
                try:
                    test_texture = CoreImage(fc.selection[0]).texture
                    if test_texture:
                        self.input_bgimg.text = fc.selection[0]
                        popup.dismiss()
                    else:
                        self.lbl_msg.text = "Файл не является изображением"
                        self.lbl_msg.color = (1, 0.5, 0, 1)
                except:
                    self.lbl_msg.text = "Ошибка: выберите другой файл"
                    self.lbl_msg.color = (1, 0.5, 0, 1)
            else:
                self.lbl_msg.text = "Файл не выбран"
                self.lbl_msg.color = (1, 0.5, 0, 1)

        btn_ok.bind(on_release=on_ok)
        btn_cancel.bind(on_release=lambda b: popup.dismiss())
        btns.add_widget(btn_ok)
        btns.add_widget(btn_cancel)
        content.add_widget(fc)
        content.add_widget(btns)
        popup.open()

    def go_back(self, instance):
        self.manager.current = 'main'

    def save_settings(self, instance):
        try:
            # === УЛУЧШЕНИЕ: защита от пустого URL ===
            api_url = self.input_url.text.strip()
            if not api_url:
                api_url = DEFAULT_API_URL
            settings.set('api_url', api_url)
            settings.set('user', self.input_user.text.strip())
            settings.set('pass', self.input_pass.text.strip())
            settings.set('interval', max(1,
                                         int(self.input_interval.text) if self.input_interval.text.strip() else DEFAULT_INTERVAL))
            settings.set('font_size',
                         max(10, int(self.input_font.text) if self.input_font.text.strip() else DEFAULT_FONT_SIZE))
            settings.set('bg_color', self.input_bg.text.strip().lstrip('#'))
            settings.set('text_color', self.input_text.text.strip().lstrip('#'))
            settings.set('bg_image', self.input_bgimg.text.strip())
            cameras = []
            for num, name, hdr, row in self.camera_rows:
                if num.text.strip():
                    cameras.append({'number': num.text.strip(), 'name': name.text.strip(), 'header': hdr.text.strip()})
            settings.set('cameras', cameras if cameras else [{'number': '', 'name': '', 'header': ''}])
            if settings.save_config():
                self.lbl_msg.text = "✓ Настройки сохранены!"
                self.lbl_msg.color = (0, 1, 0, 1)
                app = App.get_running_app()
                if app and app.root:
                    main_screen = app.root.get_screen('main')
                    if main_screen:
                        main_screen.api_client = ApiClient()
                        if main_screen._bg_initialized:
                            main_screen._apply_bg_settings()
                        else:
                            Clock.schedule_once(lambda dt: main_screen._apply_bg_settings(), 0.05)
                        main_screen._update_camera_info()
                Clock.schedule_once(lambda dt: self.go_back(None), 0.5)
            else:
                self.lbl_msg.text = "Ошибка сохранения"
                self.lbl_msg.color = (1, 0, 0, 1)
        except ValueError:
            self.lbl_msg.text = "Неверный формат данных"
            self.lbl_msg.color = (1, 0, 0, 1)
        except Exception as e:
            self.lbl_msg.text = f"Ошибка: {str(e)}"
            self.lbl_msg.color = (1, 0, 0, 1)


class ParkingTVApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(SettingsScreen(name='settings'))
        return sm


if __name__ == '__main__':
    ParkingTVApp().run()