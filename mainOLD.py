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
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.core.image import Image as CoreImage

CONFIG_FILE = 'settings.json'
DEFAULT_API_URL = "https://ucams.ufanet.ru"
DEFAULT_USER = ""
DEFAULT_PASS = ""
DEFAULT_INTERVAL = 5
DEFAULT_CAMERA = ""
DEFAULT_FONT_SIZE = 150
DEFAULT_BG_COLOR = "000000"
DEFAULT_TEXT_COLOR = "FFFFFF"
DEFAULT_HEADER_TEXT = ""
DEFAULT_HEADER_FONT_SIZE = 40
DEFAULT_BG_IMAGE = ""


class SettingsManager:
    def __init__(self):
        self.config = {
            'api_url': DEFAULT_API_URL,
            'user': DEFAULT_USER,
            'pass': DEFAULT_PASS,
            'interval': DEFAULT_INTERVAL,
            'camera_number': DEFAULT_CAMERA,
            'font_size': DEFAULT_FONT_SIZE,
            'bg_color': DEFAULT_BG_COLOR,
            'text_color': DEFAULT_TEXT_COLOR,
            'header_text': DEFAULT_HEADER_TEXT,
            'header_font_size': DEFAULT_HEADER_FONT_SIZE,
            'bg_image': DEFAULT_BG_IMAGE
        }
        self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    self.config.update(loaded)
            except Exception as e:
                print(f"Ошибка загрузки настроек: {e}")

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f)
            return True
        except Exception as e:
            print(f"Ошибка сохранения настроек: {e}")
            return False


settings = SettingsManager()


def hex_to_rgba(hex_color, alpha=1.0):
    """Конвертирует hex-цвет (#RRGGBB) в RGBA для Kivy"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return [0, 0, 0, alpha]
    return [
        int(hex_color[0:2], 16) / 255,
        int(hex_color[2:4], 16) / 255,
        int(hex_color[4:6], 16) / 255,
        alpha
    ]


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Заголовок (над основным значением)
        self.lbl_header = Label(
            text=settings.config.get('header_text', ''),
            font_size=f"{settings.config.get('header_font_size', DEFAULT_HEADER_FONT_SIZE)}sp",
            bold=True,
            color=hex_to_rgba(settings.config.get('text_color', DEFAULT_TEXT_COLOR)),
            halign='center',
            valign='middle',
            size_hint_y=None,
            height=60
        )

        # Основное значение — поле "text" из API
        self.lbl_count = Label(
            text="...",
            font_size=f"{settings.config.get('font_size', DEFAULT_FONT_SIZE)}sp",
            bold=True,
            color=hex_to_rgba(settings.config.get('text_color', DEFAULT_TEXT_COLOR)),
            halign='center',
            valign='middle'
        )

        self.lbl_status = Label(
            text="Загрузка...",
            font_size='24sp',
            color=hex_to_rgba(settings.config.get('text_color', DEFAULT_TEXT_COLOR)),
            size_hint_y=None,
            height=40
        )

        self.btn_settings = Button(
            text="Настройки",
            size_hint_y=None,
            height=60,
            font_size='24sp'
        )
        self.btn_settings.bind(on_release=self.go_to_settings)

        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        layout.add_widget(self.lbl_header)
        layout.add_widget(self.lbl_count)
        layout.add_widget(self.lbl_status)
        layout.add_widget(self.btn_settings)

        self.add_widget(layout)

        # Фон (цвет или изображение)
        with self.canvas.before:
            self.bg_color_rect = Color(*hex_to_rgba(settings.config.get('bg_color', DEFAULT_BG_COLOR)))
            self.bg_rect = Rectangle(pos=self.pos, size=self.size)
            # Изображение фона (если указано)
            self.bg_image_rect = None
            self.bg_image_texture = None

        self.bind(pos=self._update_bg, size=self._update_bg)

        self.auth_token = None
        self.update_event = None
        self._stop_fetch = False

    def _update_bg(self, *args):
        if self.bg_rect:
            self.bg_rect.pos = self.pos
            self.bg_rect.size = self.size
        if self.bg_image_rect:
            self.bg_image_rect.pos = self.pos
            self.bg_image_rect.size = self.size

    def on_enter(self, *args):
        self._stop_fetch = False
        self.apply_style()
        self.refresh_loop()

    def on_leave(self, *args):
        self._stop_fetch = True
        if self.update_event:
            self.update_event.cancel()
            self.update_event = None

    def go_to_settings(self, instance):
        self._stop_fetch = True
        if self.update_event:
            self.update_event.cancel()
            self.update_event = None
        self.manager.current = 'settings'

    def apply_style(self):
        """Применяет настройки стиля к элементам"""
        font_size = settings.config.get('font_size', DEFAULT_FONT_SIZE)
        header_font_size = settings.config.get('header_font_size', DEFAULT_HEADER_FONT_SIZE)
        text_color = hex_to_rgba(settings.config.get('text_color', DEFAULT_TEXT_COLOR))
        bg_color = hex_to_rgba(settings.config.get('bg_color', DEFAULT_BG_COLOR))
        header_text = settings.config.get('header_text', '')
        bg_image = settings.config.get('bg_image', '').strip()

        # Применяем цвета и размеры
        self.lbl_count.font_size = f"{font_size}sp"
        self.lbl_count.color = text_color
        self.lbl_header.font_size = f"{header_font_size}sp"
        self.lbl_header.color = text_color
        self.lbl_header.text = header_text
        self.lbl_status.color = text_color

        # Скрываем заголовок если пустой
        self.lbl_header.height = 60 if header_text.strip() else 0
        self.lbl_header.opacity = 1 if header_text.strip() else 0

        # Фон: изображение или цвет
        self.canvas.before.clear()
        with self.canvas.before:
            # Если есть изображение — рисуем его
            if bg_image and os.path.exists(bg_image):
                try:
                    self.bg_image_texture = CoreImage(bg_image).texture
                    self.bg_color_rect = Color(1, 1, 1, 1)
                    self.bg_rect = Rectangle(texture=self.bg_image_texture, pos=self.pos, size=self.size)
                except:
                    # Если ошибка — fallback на цвет
                    self.bg_color_rect = Color(*bg_color)
                    self.bg_rect = Rectangle(pos=self.pos, size=self.size)
            else:
                # Иначе просто цвет
                self.bg_color_rect = Color(*bg_color)
                self.bg_rect = Rectangle(pos=self.pos, size=self.size)

        self.bind(pos=self._update_bg, size=self._update_bg)

    def refresh_loop(self, dt=None):
        if self._stop_fetch:
            return
        threading.Thread(target=self.fetch_data, daemon=True).start()
        if self.update_event:
            self.update_event.cancel()
        interval = settings.config.get('interval', 5)
        self.update_event = Clock.schedule_once(lambda dt: self._refresh_loop_wrapper(), interval)

    def _refresh_loop_wrapper(self, dt=None):
        if not self._stop_fetch:
            self.refresh_loop()

    def fetch_data(self):
        if self._stop_fetch:
            return
        try:
            # 1. Авторизация
            if not self.auth_token:
                auth_url = f"{settings.config.get('api_url', DEFAULT_API_URL)}/api/v0/auth/"
                auth_data = {
                    "username": settings.config.get('user', ''),
                    "password": settings.config.get('pass', '')
                }
                resp = requests.post(auth_url, json=auth_data, verify=False, timeout=10)

                if resp.status_code == 200:
                    data = resp.json()
                    self.auth_token = data.get('access_token') or data.get('token') or data.get('access')
                    if not self.auth_token:
                        Clock.schedule_once(lambda dt: self._set_status("Ошибка: Токен не получен"))
                        return
                else:
                    Clock.schedule_once(lambda dt: self._set_status(f"Ошибка входа: {resp.status_code}"))
                    return

            # 2. Формируем правильный запрос к API
            report_url = f"{settings.config.get('api_url', DEFAULT_API_URL)}/api/v0/analytics/parking_detection/report/"
            headers = {
                'Authorization': f'Bearer {self.auth_token}',
                'Content-Type': 'application/json'
            }

            # Временной диапазон: последние 24 часа в формате ISO 8601
            now = datetime.now(timezone.utc)
            start_time = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

            camera = settings.config.get('camera_number', '').strip()

            # Правильный формат запроса как в примере
            payload = {
                "page": 1,
                "page_size": 10,
                "start": start_time,
                "end": end_time,
                "query": "",
                "ordering": [{"sort": "id", "order": "DESC"}],
                "camera_number": camera
            }

            print(f"Sending payload: {json.dumps(payload, ensure_ascii=False)[:300]}")

            resp = requests.post(report_url, headers=headers, json=payload, verify=False, timeout=10)

            # Отладочный лог
            print(f"Report response: {resp.status_code} - {resp.text[:500]}")

            if resp.status_code == 200:
                data = resp.json()
                display_text = ""

                # Пробуем извлечь поле "text" из ответа
                if isinstance(data, dict):
                    # Если есть поле "text" напрямую
                    if "text" in data:
                        display_text = str(data["text"])
                    # Если есть результаты в поле "results" или "data"
                    elif "results" in data and isinstance(data["results"], list) and len(data["results"]) > 0:
                        first_item = data["results"][0]
                        if isinstance(first_item, dict) and "text" in first_item:
                            display_text = str(first_item["text"])
                    # Если есть поле "count" — показываем его как запасной вариант
                    elif "count" in data:
                        display_text = str(data["count"])
                elif isinstance(data, list) and len(data) > 0:
                    first_item = data[0]
                    if isinstance(first_item, dict) and "text" in first_item:
                        display_text = str(first_item["text"])

                # Если ничего не нашли — показываем сырой ответ для отладки
                if not display_text:
                    display_text = json.dumps(data, ensure_ascii=False)[:100]

                Clock.schedule_once(lambda dt: self._update_ui(display_text))
            else:
                Clock.schedule_once(lambda dt: self._set_status(f"Ошибка API: {resp.status_code}"))

        except Exception as e:
            Clock.schedule_once(lambda dt: self._set_status(f"Ошибка: {e}"))

    def _set_status(self, text):
        self.lbl_status.text = text

    def _update_ui(self, text):
        if not self._stop_fetch:
            # Отображаем только текст, без префиксов
            self.lbl_count.text = str(text)
            now = datetime.now().strftime("%H:%M:%S")
            self.lbl_status.text = f"Обновлено: {now}"


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=10)

        # API и авторизация
        self.input_url = TextInput(hint_text="URL API", text=settings.config.get('api_url', ''),
                                   multiline=False, font_size='14sp')
        self.input_user = TextInput(hint_text="Логин", text=settings.config.get('user', ''),
                                    multiline=False, font_size='14sp')
        self.input_pass = TextInput(hint_text="Пароль", text=settings.config.get('pass', ''),
                                    password=True, multiline=False, font_size='14sp')
        self.input_camera = TextInput(hint_text="Номер камеры *", text=settings.config.get('camera_number', ''),
                                      multiline=False, font_size='14sp')

        # Интервал обновления
        self.input_interval = TextInput(hint_text="Интервал (сек)",
                                        text=str(settings.config.get('interval', 5)),
                                        input_filter='int', multiline=False, font_size='14sp')

        # Заголовок (текст над значением)
        self.input_header = TextInput(hint_text="Заголовок (над значением)",
                                      text=settings.config.get('header_text', ''),
                                      multiline=False, font_size='14sp')
        self.input_header_font = TextInput(hint_text="Размер шрифта заголовка",
                                           text=str(settings.config.get('header_font_size', DEFAULT_HEADER_FONT_SIZE)),
                                           input_filter='int', multiline=False, font_size='14sp')

        # Основное значение
        self.input_font_size = TextInput(hint_text="Размер шрифта значения",
                                         text=str(settings.config.get('font_size', DEFAULT_FONT_SIZE)),
                                         input_filter='int', multiline=False, font_size='14sp')

        # Цвета
        self.input_bg = TextInput(hint_text="Цвет фона (hex, напр. 000000)",
                                  text=settings.config.get('bg_color', DEFAULT_BG_COLOR),
                                  multiline=False, font_size='14sp')
        self.input_text = TextInput(hint_text="Цвет текста (hex, напр. FFFFFF)",
                                    text=settings.config.get('text_color', DEFAULT_TEXT_COLOR),
                                    multiline=False, font_size='14sp')

        # Фоновое изображение (путь к файлу на устройстве)
        self.input_bg_image = TextInput(hint_text="Путь к фоновому изображению (напр. /sdcard/bg.png)",
                                        text=settings.config.get('bg_image', ''),
                                        multiline=False, font_size='14sp')

        self.lbl_msg = Label(text="", color=(1, 0.5, 0.5, 1), size_hint_y=None, height=30)

        btn_save = Button(text="Сохранить", size_hint_y=None, height=60, font_size='24sp')
        btn_save.bind(on_release=self.save_settings)

        btn_back = Button(text="Назад", size_hint_y=None, height=60, font_size='24sp')
        btn_back.bind(on_release=self.go_back)

        # Добавляем виджеты в layout
        self.layout.add_widget(self.input_url)
        self.layout.add_widget(self.input_user)
        self.layout.add_widget(self.input_pass)
        self.layout.add_widget(self.input_camera)
        self.layout.add_widget(self.input_interval)
        self.layout.add_widget(Label(text="--- Заголовок ---", size_hint_y=None, height=30))
        self.layout.add_widget(self.input_header)
        self.layout.add_widget(self.input_header_font)
        self.layout.add_widget(Label(text="--- Основное значение ---", size_hint_y=None, height=30))
        self.layout.add_widget(self.input_font_size)
        self.layout.add_widget(Label(text="--- Оформление ---", size_hint_y=None, height=30))
        self.layout.add_widget(self.input_bg)
        self.layout.add_widget(self.input_text)
        self.layout.add_widget(self.input_bg_image)
        self.layout.add_widget(self.lbl_msg)
        self.layout.add_widget(btn_save)
        self.layout.add_widget(btn_back)
        self.add_widget(self.layout)

    def go_back(self, instance):
        self.manager.current = 'main'

    def save_settings(self, instance):
        try:
            settings.config['api_url'] = self.input_url.text.strip()
            settings.config['user'] = self.input_user.text.strip()
            settings.config['pass'] = self.input_pass.text.strip()
            settings.config['camera_number'] = self.input_camera.text.strip()
            settings.config['interval'] = int(self.input_interval.text)
            settings.config['header_text'] = self.input_header.text.strip()
            settings.config['header_font_size'] = int(self.input_header_font.text)
            settings.config['font_size'] = int(self.input_font_size.text)
            settings.config['bg_color'] = self.input_bg.text.strip().lstrip('#')
            settings.config['text_color'] = self.input_text.text.strip().lstrip('#')
            settings.config['bg_image'] = self.input_bg_image.text.strip()

            if settings.save_config():
                self.lbl_msg.text = "Сохранено! Перезапустите приложение."
                self.lbl_msg.color = (0, 1, 0, 1)
                app = App.get_running_app()
                if app and app.root:
                    main_scr = app.root.get_screen('main')
                    if main_scr:
                        main_scr.auth_token = None
                        main_scr.apply_style()
            else:
                self.lbl_msg.text = "Ошибка сохранения"
                self.lbl_msg.color = (1, 0, 0, 1)
        except ValueError:
            self.lbl_msg.text = "Неверный формат числа"
            self.lbl_msg.color = (1, 0, 0, 1)


class ParkingTVApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(SettingsScreen(name='settings'))
        return sm


if __name__ == '__main__':
    ParkingTVApp().run()