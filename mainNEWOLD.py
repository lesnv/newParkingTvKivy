import os
import json
import requests
import threading
from datetime import datetime, timedelta, timezone

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.core.image import Image as CoreImage
from kivy.utils import platform

CONFIG_FILE = 'settings.json'
DEFAULT_API_URL = "https://ucams.ufanet.ru"
DEFAULT_USER = ""
DEFAULT_PASS = ""
DEFAULT_INTERVAL = 5
DEFAULT_CAMERAS = [{"number": "", "name": "", "header": ""}]
DEFAULT_FONT_SIZE = 150
DEFAULT_BG_COLOR = "000000"
DEFAULT_TEXT_COLOR = "FFFFFF"
DEFAULT_BG_IMAGE = ""

COLOR_PRESETS = [
    ("000000", "Чёрный"), ("FFFFFF", "Белый"), ("FF0000", "Красный"),
    ("00FF00", "Зелёный"), ("0000FF", "Синий"), ("FFFF00", "Жёлтый"),
    ("00FFFF", "Голубой"), ("FF00FF", "Пурпурный"), ("808080", "Серый"),
    ("800000", "Бордо"), ("008000", "Тёмно-зелёный"), ("000080", "Тёмно-синий"),
    ("808000", "Оливковый"), ("800080", "Фиолетовый"), ("008080", "Бирюзовый"),
    ("FFA500", "Оранжевый"), ("FFC0CB", "Розовый"), ("A52A2A", "Коричневый"),
    ("C0C0C0", "Серебро"), ("FFD700", "Золото")
]


class SettingsManager:
    def __init__(self):
        self.config = {
            'api_url': DEFAULT_API_URL, 'user': DEFAULT_USER, 'pass': DEFAULT_PASS,
            'interval': DEFAULT_INTERVAL, 'cameras': DEFAULT_CAMERAS,
            'font_size': DEFAULT_FONT_SIZE, 'bg_color': DEFAULT_BG_COLOR,
            'text_color': DEFAULT_TEXT_COLOR, 'bg_image': DEFAULT_BG_IMAGE
        }
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    for key in loaded:
                        if key == 'cameras' and isinstance(loaded[key], list):
                            self.config['cameras'] = loaded[key]
                        else:
                            self.config[key] = loaded[key]
            except Exception as e:
                print(f"Ошибка загрузки: {e}")

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Ошибка сохранения: {e}")
            return False


settings = SettingsManager()


def hex_to_rgba(hex_color, alpha=1.0):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return [0, 0, 0, alpha]
    return [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)] + [alpha]


def rgba_to_hex(rgba):
    return f"{int(rgba[0] * 255):02X}{int(rgba[1] * 255):02X}{int(rgba[2] * 255):02X}"


class ColorPickerPopup(Popup):
    def __init__(self, current_color, on_select, **kwargs):
        super().__init__(**kwargs)
        self.on_select = on_select
        self.title = "Выберите цвет"
        self.size_hint = (0.9, 0.7)
        layout = BoxLayout(orientation='vertical', spacing=10, padding=20)
        grid = BoxLayout(cols=5, spacing=10)
        for hex_val, name in COLOR_PRESETS:
            btn = Button(text=name, background_color=hex_to_rgba(hex_val),
                         color=hex_to_rgba(
                             "FFFFFF" if hex_val in ["000000", "800000", "008000", "000080", "808000", "800080",
                                                     "008080", "A52A2A"] else "000000"),
                         font_size='10sp')
            btn.bind(on_release=lambda btn, h=hex_val: self._select(h))
            grid.add_widget(btn)
        scroll = ScrollView()
        scroll.add_widget(grid)
        layout.add_widget(scroll)
        self.content = layout

    def _select(self, hex_val):
        if self.on_select: self.on_select(hex_val)
        self.dismiss()


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.lbl_header = Label(text="", font_size='40sp', bold=True,
                                color=hex_to_rgba(settings.config.get('text_color', DEFAULT_TEXT_COLOR)),
                                halign='center', valign='middle', size_hint_y=None, height=50)
        self.lbl_count = Label(text="...",
                               font_size=f"{settings.config.get('font_size', DEFAULT_FONT_SIZE)}sp", bold=True,
                               color=hex_to_rgba(settings.config.get('text_color', DEFAULT_TEXT_COLOR)),
                               halign='center', valign='middle')
        self.lbl_status = Label(text="Загрузка...", font_size='20sp',
                                color=hex_to_rgba(settings.config.get('text_color', DEFAULT_TEXT_COLOR)),
                                size_hint_y=None, height=35)
        self.btn_settings = Button(text="⚙ Настройки", size_hint_y=None, height=50, font_size='20sp')
        self.btn_settings.bind(on_release=self.go_to_settings)
        layout = BoxLayout(orientation='vertical', padding=15, spacing=15)
        layout.add_widget(self.lbl_header)
        layout.add_widget(self.lbl_count)
        layout.add_widget(self.lbl_status)
        layout.add_widget(self.btn_settings)
        self.add_widget(layout)
        with self.canvas.before:
            self.bg_color_instruction = Color(*hex_to_rgba(settings.config.get('bg_color', DEFAULT_BG_COLOR)))
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)
        self.auth_token = None
        self.update_event = None
        self._stop_fetch = False
        self._token_refreshing = False
        self._current_camera_idx = 0

    def _update_bg(self, *args):
        if self.bg_rect: self.bg_rect.pos, self.bg_rect.size = self.pos, self.size

    def on_enter(self, *args):
        self._stop_fetch = False
        self.apply_style()
        self.refresh_loop()

    def on_leave(self, *args):
        self._stop_fetch = True
        if self.update_event: self.update_event.cancel(); self.update_event = None

    def go_to_settings(self, instance):
        self._stop_fetch = True
        if self.update_event: self.update_event.cancel(); self.update_event = None
        self.manager.current = 'settings'

    def apply_style(self):
        fs = settings.config.get('font_size', DEFAULT_FONT_SIZE)
        tc = hex_to_rgba(settings.config.get('text_color', DEFAULT_TEXT_COLOR))
        bc = hex_to_rgba(settings.config.get('bg_color', DEFAULT_BG_COLOR))
        bi = settings.config.get('bg_image', '').strip()
        self.lbl_count.font_size = f"{fs}sp"
        self.lbl_count.color = tc
        self.lbl_header.color = tc
        self.lbl_status.color = tc
        if self.bg_color_instruction and self.bg_rect:
            if bi and os.path.exists(bi):
                try:
                    self.bg_rect.texture = CoreImage(bi).texture
                    self.bg_color_instruction.rgba = [1, 1, 1, 1]
                except:
                    self.bg_rect.texture = None; self.bg_color_instruction.rgba = bc
            else:
                self.bg_rect.texture = None; self.bg_color_instruction.rgba = bc

    def refresh_loop(self, dt=None):
        if self._stop_fetch: return
        threading.Thread(target=self.fetch_data, daemon=True).start()
        if self.update_event: self.update_event.cancel()
        interval = settings.config.get('interval', 5)
        self.update_event = Clock.schedule_once(lambda dt: self._refresh_loop_wrapper(), interval)

    def _refresh_loop_wrapper(self, dt=None):
        if not self._stop_fetch: self.refresh_loop()

    def get_auth_token(self):
        try:
            auth_url = f"{settings.config.get('api_url', DEFAULT_API_URL)}/api/v0/auth/"
            resp = requests.post(auth_url, json={"username": settings.config.get('user', ''),
                                                 "password": settings.config.get('pass', '')}, verify=False, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                token = data.get('access_token') or data.get('token') or data.get('access')
                print(f"Token obtained")
                return token
            print(f"Auth failed: {resp.status_code}")
            return None
        except Exception as e:
            print(f"Auth error: {e}")
            return None

    def fetch_data(self, retry_count=0):
        if self._stop_fetch: return
        MAX_RETRY = 2
        try:
            if not self.auth_token:
                self.auth_token = self.get_auth_token()
                if not self.auth_token:
                    Clock.schedule_once(lambda dt: self._set_status("Ошибка авторизации"))
                    return
            cameras = settings.config.get('cameras', [])
            if not cameras or not cameras[0].get('number'):
                Clock.schedule_once(lambda dt: self._set_status("Укажите номер камеры"))
                return
            camera = cameras[self._current_camera_idx].get('number', '').strip()
            header = cameras[self._current_camera_idx].get('header', '').strip()
            Clock.schedule_once(lambda dt: setattr(self.lbl_header, 'text', header))
            report_url = f"{settings.config.get('api_url', DEFAULT_API_URL)}/api/v0/analytics/parking_detection/report/"
            headers = {'Authorization': f'Bearer {self.auth_token}', 'Content-Type': 'application/json'}
            now = datetime.now(timezone.utc)
            payload = {"page": 1, "page_size": 10, "start": (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "end": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "query": "",
                       "ordering": [{"sort": "id", "order": "DESC"}], "camera_number": camera}
            print(f"Sending: {camera}")
            resp = requests.post(report_url, headers=headers, json=payload, verify=False, timeout=10)
            print(f"Response: {resp.status_code} - {resp.text[:300]}")
            if resp.status_code == 200:
                data = resp.json()
                display_text = ""
                if isinstance(data, dict):
                    if "text" in data:
                        display_text = str(data["text"])
                    elif "results" in data and data["results"] and "text" in data["results"][0]:
                        display_text = str(data["results"][0]["text"])
                    elif "count" in data:
                        display_text = str(data["count"])
                elif isinstance(data, list) and data and "text" in data[0]:
                    display_text = str(data[0]["text"])
                if not display_text: display_text = json.dumps(data, ensure_ascii=False)[:100]
                Clock.schedule_once(lambda dt: self._update_ui(display_text))
            elif resp.status_code == 401 and retry_count < MAX_RETRY and not self._token_refreshing:
                self._token_refreshing = True
                self.auth_token = None
                new_token = self.get_auth_token()
                self._token_refreshing = False
                if new_token:
                    self.auth_token = new_token
                    self.fetch_data(retry_count + 1)
                else:
                    Clock.schedule_once(lambda dt: self._set_status("Токен не обновлён"))
            else:
                Clock.schedule_once(lambda dt: self._set_status(f"Ошибка: {resp.status_code}"))
        except Exception as e:
            Clock.schedule_once(lambda dt: self._set_status(f"Ошибка: {e}"))

    def _set_status(self, text):
        self.lbl_status.text = text

    def _update_ui(self, text):
        if not self._stop_fetch:
            self.lbl_count.text = str(text)
            self.lbl_status.text = f"Обновлено: {datetime.now().strftime('%H:%M:%S')}"


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.camera_rows = []
        self.build_ui()

    def build_ui(self):
        # Основной контейнер с прокруткой
        main_layout = BoxLayout(orientation='vertical', padding=15, spacing=10)
        scroll = ScrollView()
        content = BoxLayout(orientation='vertical', padding=10, spacing=8, size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        # API настройки
        main_layout.add_widget(Label(text="🔗 API", size_hint_y=None, height=30, bold=True))
        self.input_url = TextInput(hint_text="URL API", text=settings.config.get('api_url', ''), multiline=False,
                                   font_size='14sp')
        self.input_user = TextInput(hint_text="Логин", text=settings.config.get('user', ''), multiline=False,
                                    font_size='14sp')
        self.input_pass = TextInput(hint_text="Пароль", password=True, text=settings.config.get('pass', ''),
                                    multiline=False, font_size='14sp')
        main_layout.add_widget(self.input_url)
        main_layout.add_widget(self.input_user)
        main_layout.add_widget(self.input_pass)

        # Камеры
        main_layout.add_widget(Label(text="📷 Камеры", size_hint_y=None, height=30, bold=True))
        self.camera_container = BoxLayout(orientation='vertical', spacing=5)
        main_layout.add_widget(self.camera_container)
        btn_add = Button(text="+ Добавить камеру", size_hint_y=None, height=40, font_size='16sp')
        btn_add.bind(on_release=self.add_camera_row)
        main_layout.add_widget(btn_add)

        # Общие настройки
        main_layout.add_widget(Label(text="⚙ Общие настройки", size_hint_y=None, height=30, bold=True))
        self.input_interval = TextInput(hint_text="Интервал (сек)", text=str(settings.config.get('interval', 5)),
                                        input_filter='int', multiline=False, font_size='14sp')
        self.input_font = TextInput(hint_text="Размер шрифта", text=str(settings.config.get('font_size', 150)),
                                    input_filter='int', multiline=False, font_size='14sp')

        # Цвета
        bg_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)
        self.input_bg = TextInput(hint_text="Цвет фона (hex)", text=settings.config.get('bg_color', DEFAULT_BG_COLOR),
                                  readonly=True, multiline=False, font_size='14sp')
        self.btn_bg = Button(text="■", font_size='18sp',
                             background_color=hex_to_rgba(settings.config.get('bg_color', DEFAULT_BG_COLOR)))
        self.btn_bg.bind(on_release=lambda b: self.open_color_picker(self.input_bg, self.btn_bg))
        bg_layout.add_widget(self.input_bg);
        bg_layout.add_widget(self.btn_bg)

        text_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)
        self.input_text = TextInput(hint_text="Цвет текста (hex)",
                                    text=settings.config.get('text_color', DEFAULT_TEXT_COLOR), readonly=True,
                                    multiline=False, font_size='14sp')
        self.btn_text = Button(text="■", font_size='18sp',
                               background_color=hex_to_rgba(settings.config.get('text_color', DEFAULT_TEXT_COLOR)))
        self.btn_text.bind(on_release=lambda b: self.open_color_picker(self.input_text, self.btn_text))
        text_layout.add_widget(self.input_text);
        text_layout.add_widget(self.btn_text)

        # Фон изображение
        self.input_bgimg = TextInput(hint_text="Путь к фону (/sdcard/bg.png)", text=settings.config.get('bg_image', ''),
                                     readonly=True, multiline=False, font_size='14sp')
        btn_pick = Button(text="📁 Выбрать файл", size_hint_y=None, height=40, font_size='14sp')
        btn_pick.bind(on_release=self.select_image)

        main_layout.add_widget(self.input_interval)
        main_layout.add_widget(self.input_font)
        main_layout.add_widget(bg_layout)
        main_layout.add_widget(text_layout)
        main_layout.add_widget(self.input_bgimg)
        main_layout.add_widget(btn_pick)

        # Кнопки
        btn_layout = BoxLayout(size_hint_y=None, height=60, spacing=10, padding=(0, 10, 0, 0))
        btn_save = Button(text="💾 Сохранить", font_size='18sp')
        btn_save.bind(on_release=self.save_settings)
        btn_back = Button(text="⬅ Назад", font_size='18sp')
        btn_back.bind(on_release=self.go_back)
        btn_layout.add_widget(btn_save);
        btn_layout.add_widget(btn_back)
        main_layout.add_widget(btn_layout)
        self.lbl_msg = Label(text="", color=(1, 0.5, 0.5, 1), size_hint_y=None, height=30)
        main_layout.add_widget(self.lbl_msg)

        content.add_widget(main_layout)
        scroll.add_widget(content)
        self.add_widget(scroll)

        # Заполняем камеры
        for cam in settings.config.get('cameras', DEFAULT_CAMERAS):
            self.add_camera_row(None, cam.get('number', ''), cam.get('name', ''), cam.get('header', ''))

    def add_camera_row(self, instance, number='', name='', header=''):
        row = BoxLayout(orientation='vertical', size_hint_y=None, height=130, spacing=3, padding=(0, 5))
        row.bg = Color(0.2, 0.2, 0.25, 0.3)
        with row.canvas.before: Rectangle(pos=row.pos, size=row.size, color=row.bg)
        row.bind(pos=lambda *a: setattr(row.canvas.before.children[0], 'pos',
                                        row.pos) if row.canvas.before.children else None,
                 size=lambda *a: setattr(row.canvas.before.children[0], 'size',
                                         row.size) if row.canvas.before.children else None)

        top = BoxLayout(size_hint_y=None, height=32, spacing=5)
        inp_num = TextInput(hint_text="Номер камеры *", text=number, multiline=False, font_size='13sp')
        inp_name = TextInput(hint_text="Название", text=name, multiline=False, font_size='13sp')
        top.add_widget(inp_num);
        top.add_widget(inp_name)

        mid = BoxLayout(size_hint_y=None, height=32, spacing=5)
        inp_hdr = TextInput(hint_text="Заголовок для этой камеры", text=header, multiline=False, font_size='13sp')
        btn_del = Button(text="✕", size_hint_x=None, width=35, font_size='16sp', background_color=(1, 0.3, 0.3, 1))
        btn_del.bind(on_release=lambda b: self.remove_camera_row(row))
        mid.add_widget(inp_hdr);
        mid.add_widget(btn_del)

        row.add_widget(top);
        row.add_widget(mid)
        self.camera_container.add_widget(row)
        self.camera_rows.append((inp_num, inp_name, inp_hdr))

    def remove_camera_row(self, row_widget):
        if row_widget in self.camera_container.children:
            self.camera_container.remove_widget(row_widget)
            for i, (n, name, hdr) in enumerate(self.camera_rows):
                if n.parent and n.parent.parent == row_widget:
                    self.camera_rows.pop(i);
                    break

    def open_color_picker(self, text_input, color_btn):
        def on_select(hex_val):
            text_input.text = hex_val
            color_btn.background_color = hex_to_rgba(hex_val)

        ColorPickerPopup(settings.config.get('text_color', DEFAULT_TEXT_COLOR), on_select).open()

    def select_image(self, instance):
        from kivy.uix.filechooser import FileChooserListView
        start_path = '/sdcard/' if platform == 'android' else os.path.expanduser('~')
        content = BoxLayout(orientation='vertical')
        fc = FileChooserListView(path=start_path, filters=['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.gif'],
                                 filter_dirs=True)
        btns = BoxLayout(size_hint_y=None, height=45, spacing=10)
        btn_ok = Button(text="Выбрать");
        btn_cancel = Button(text="Отмена")

        def on_ok(b):
            if fc.selection: self.input_bgimg.text = fc.selection[0]; popup.dismiss()

        btn_ok.bind(on_release=on_ok);
        btn_cancel.bind(on_release=lambda b: popup.dismiss())
        btns.add_widget(btn_ok);
        btns.add_widget(btn_cancel)
        content.add_widget(fc);
        content.add_widget(btns)
        popup = Popup(title="Выберите изображение", content=content, size_hint=(0.95, 0.85))
        popup.open()

    def go_back(self, instance):
        self.manager.current = 'main'

    def save_settings(self, instance):
        try:
            settings.config['api_url'] = self.input_url.text.strip()
            settings.config['user'] = self.input_user.text.strip()
            settings.config['pass'] = self.input_pass.text.strip()
            settings.config['interval'] = int(self.input_interval.text)
            settings.config['font_size'] = int(self.input_font.text)
            settings.config['bg_color'] = self.input_bg.text.strip().lstrip('#')
            settings.config['text_color'] = self.input_text.text.strip().lstrip('#')
            settings.config['bg_image'] = self.input_bgimg.text.strip()
            cams = []
            for num, name, hdr in self.camera_rows:
                if num.text.strip(): cams.append(
                    {'number': num.text.strip(), 'name': name.text.strip(), 'header': hdr.text.strip()})
            if not cams: cams = [{'number': '', 'name': '', 'header': ''}]
            settings.config['cameras'] = cams
            if settings.save_config():
                self.lbl_msg.text = "✓ Сохранено! Перезапустите приложение."
                self.lbl_msg.color = (0, 1, 0, 1)
                app = App.get_running_app()
                if app and app.root:
                    ms = app.root.get_screen('main')
                    if ms: ms.auth_token = None; ms.apply_style()
            else:
                self.lbl_msg.text = "Ошибка сохранения"; self.lbl_msg.color = (1, 0, 0, 1)
        except ValueError:
            self.lbl_msg.text = "Неверный формат числа"; self.lbl_msg.color = (1, 0, 0, 1)


class ParkingTVApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(SettingsScreen(name='settings'))
        return sm


if __name__ == '__main__':
    ParkingTVApp().run()