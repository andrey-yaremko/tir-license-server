import customtkinter as ctk
from PIL import Image, ImageTk
import requests
import json
import hashlib
import uuid
import os
import sys
import subprocess
import threading
import zipfile
import shutil
from datetime import datetime

# 🎨 КОЛЬОРИ
COLOR_PRIMARY_DARK = "#1a1a1a"
COLOR_BACKGROUND_DARK = "#0d0d0d"
COLOR_SURFACE_DARK = "#2d2d2d"
COLOR_ON_SURFACE_DARK = "#ffffff"
COLOR_TEXT_SECONDARY = "#888888"
COLOR_ACCENT_GREEN = "#2e7d32"
COLOR_OUTLINE_DARK = "#404040"
COLOR_ACTIVE_ITEM = "#3d3d3d"
COLOR_BUTTON_ACTIVE = "#2e7d32"
COLOR_START_ACTIVE = "#d32f2f"
COLOR_BUTTON_LIGHTER = "#3d3d3d"
COLOR_BORDER_ACTIVE = "#4CAF50"

# 🌐 НАЛАШТУВАННЯ СЕРВЕРА
SERVER_URL = "https://web-production-83b9.up.railway.app"

class TIRLauncher:
    def __init__(self):
        print("🎮 Запуск TIR Bot Launcher (Final Release)...")
        
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        self.root = ctk.CTk()
        self.root.title("TIR Bot Launcher")
        self.root.geometry("500x650")
        self.root.resizable(False, False)
        
        # === 🔧 ВАЖЛИВЕ ВИПРАВЛЕННЯ ШЛЯХІВ ===
        # Це гарантує, що файли зберігаються поруч з EXE, а не в тимчасовій папці
        if getattr(sys, 'frozen', False):
            self.launcher_dir = os.path.dirname(sys.executable)
        else:
            self.launcher_dir = os.path.dirname(os.path.abspath(__file__))
            
        print(f"📁 Робоча папка: {self.launcher_dir}")

        # Стани
        self.license_key = ""
        self.hwid = self.generate_hwid()
        self.is_activated = False
        self.activation_data = {}
        self.bot_downloaded = False
        self.drivers_installed = False
        
        # 🎯 ШЛЯХИ
        self.bot_dir = os.path.join(self.launcher_dir, "TIR_Bot_Full")
        self.bot_executable = "TIR_Bot.exe"
        self.bot_full_path = os.path.join(self.bot_dir, self.bot_executable)
        self.drivers_dir = os.path.join(self.bot_dir, "Drivers")
        self.install_drivers_bat = os.path.join(self.drivers_dir, "install_drivers.bat")
        
        # Завантаження налаштувань
        self.load_activation_state()
        
        # Перевірка файлів
        self.check_bot_downloaded()
        
        # GUI
        self.setup_gui()
        
        if self.is_activated:
            self.show_main_screen()

    def check_bot_downloaded(self):
        self.bot_downloaded = os.path.exists(self.bot_full_path)
        if self.bot_downloaded:
            print("✅ Файли бота знайдені")
        else:
            print("📥 Файли бота відсутні")

    def generate_hwid(self):
        try:
            import platform
            import psutil
            system_info = f"{platform.node()}{platform.processor()}{psutil.disk_partitions()[0].device}"
            hwid = hashlib.md5(system_info.encode()).hexdigest()
            return hwid
        except:
            return hashlib.md5(str(uuid.getnode()).encode()).hexdigest()

    def load_activation_state(self):
        try:
            activation_file = os.path.join(self.launcher_dir, "activation.json")
            if os.path.exists(activation_file):
                with open(activation_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.license_key = data.get("license_key", "")
                    
                    # Перевіряємо HWID (захист від копіювання файлу на інший ПК)
                    if data.get("hwid") == self.hwid:
                        self.is_activated = data.get("is_activated", False)
                        self.activation_data = data.get("activation_data", {})
                        self.drivers_installed = data.get("drivers_installed", False)
                    else:
                        print("⚠️ HWID змінився, потрібна повторна активація")
        except Exception as e:
            print(f"❌ Помилка завантаження конфігу: {e}")

    def save_activation_state(self):
        try:
            activation_file = os.path.join(self.launcher_dir, "activation.json")
            data = {
                "license_key": self.license_key,
                "hwid": self.hwid,
                "is_activated": self.is_activated,
                "activation_data": self.activation_data,
                "last_check": datetime.now().isoformat(),
                "drivers_installed": self.drivers_installed
            }
            with open(activation_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Помилка збереження конфігу: {e}")

    def setup_gui(self):
        main_frame = ctk.CTkFrame(self.root, fg_color=COLOR_BACKGROUND_DARK, corner_radius=0)
        main_frame.pack(fill="both", expand=True, padx=0, pady=0)

        app_bar = ctk.CTkFrame(main_frame, fg_color=COLOR_PRIMARY_DARK, height=60, corner_radius=0)
        app_bar.pack(fill='x')
        app_bar.pack_propagate(False)

        title_label = ctk.CTkLabel(app_bar, text="TIR Bot Launcher", text_color=COLOR_ON_SURFACE_DARK, fg_color=COLOR_PRIMARY_DARK, font=("Inter", 16, "bold"))
        title_label.pack(side="left", padx=20, pady=10)

        self.content_frame = ctk.CTkFrame(main_frame, fg_color=COLOR_BACKGROUND_DARK, corner_radius=0)
        self.content_frame.pack(fill='both', expand=True, padx=20, pady=20)

        if not self.is_activated:
            self.show_activation_screen()
        else:
            self.show_main_screen()

    def show_activation_screen(self):
        for widget in self.content_frame.winfo_children(): widget.destroy()

        main_card = ctk.CTkFrame(self.content_frame, fg_color=COLOR_PRIMARY_DARK, corner_radius=12)
        main_card.pack(fill='x', pady=10, padx=0)

        ctk.CTkLabel(main_card, text="🔐 АКТИВАЦІЯ TIR BOT", text_color=COLOR_ON_SURFACE_DARK, font=("Inter", 18, "bold")).pack(pady=(20, 10))
        ctk.CTkLabel(main_card, text="Введіть ваш ключ ліцензії", text_color=COLOR_TEXT_SECONDARY).pack(pady=(0, 20))

        self.key_entry = ctk.CTkEntry(main_card, placeholder_text="Введіть ключ...", width=400, height=45)
        self.key_entry.pack(pady=10, padx=20)
        self.key_entry.bind('<Return>', lambda e: self.activate_license())
        
        self.activate_button = ctk.CTkButton(main_card, text="🎮 АКТИВУВАТИ", fg_color=COLOR_BUTTON_ACTIVE, height=45, command=self.activate_license)
        self.activate_button.pack(pady=10, padx=20, fill='x')

        self.status_label = ctk.CTkLabel(main_card, text="", text_color=COLOR_TEXT_SECONDARY)
        self.status_label.pack(pady=(10, 20))

        ctk.CTkLabel(self.content_frame, text=f"HWID: {self.hwid}", text_color="gray", font=("Arial", 10)).pack(side="bottom", pady=10)

    def show_main_screen(self):
        for widget in self.content_frame.winfo_children(): widget.destroy()

        main_card = ctk.CTkFrame(self.content_frame, fg_color=COLOR_PRIMARY_DARK, corner_radius=12)
        main_card.pack(fill='x', pady=10, padx=0)

        ctk.CTkLabel(main_card, text="✅ TIR BOT АКТИВОВАНО", text_color=COLOR_ACCENT_GREEN, font=("Inter", 18, "bold")).pack(pady=(20, 10))

        lic_info = self.activation_data.get('license_info', {})
        expires_at = lic_info.get('expires_at', 'Невідомо')
        days_left = lic_info.get('days_left', 'Невідомо')
        
        # Обробка формату дати (обрізаємо час)
        if "T" in str(expires_at): expires_at = str(expires_at).split("T")[0]

        drivers_status = "✅ Встановлені" if self.drivers_installed else "📥 Потрібно встановити"
        
        info_text = f"📅 Дійсна до: {expires_at}\n⏰ Днів: {days_left}\n🔑 Ключ: {self.license_key[:10]}...\n🔌 Драйвера: {drivers_status}"
        
        ctk.CTkLabel(main_card, text=info_text, justify="left").pack(pady=10, padx=20)

        if not self.bot_downloaded:
            self.progress_bar = ctk.CTkProgressBar(main_card, progress_color=COLOR_ACCENT_GREEN)
            self.progress_bar.pack(pady=10, padx=20, fill='x')
            self.progress_bar.set(0)
            self.progress_label = ctk.CTkLabel(main_card, text="Готово до завантаження")
            self.progress_label.pack(pady=(0, 10))

        btn_text = "🚀 ЗАПУСТИТИ TIR BOT" if self.bot_downloaded else "📥 ЗАВАНТАЖИТИ ТА ЗАПУСТИТИ"
        self.launch_button = ctk.CTkButton(main_card, text=btn_text, fg_color=COLOR_BUTTON_ACTIVE, height=50, font=("Inter", 14, "bold"), command=self.launch_bot)
        self.launch_button.pack(pady=20, padx=20, fill='x')

        ctk.CTkButton(main_card, text="🔄 ПЕРЕВІРИТИ СТАТУС", fg_color=COLOR_SURFACE_DARK, command=self.check_license_status).pack(pady=(0, 10), padx=20, fill='x')
        ctk.CTkButton(main_card, text="🗑️ ДЕАКТИВУВАТИ", fg_color=COLOR_START_ACTIVE, command=self.deactivate_license).pack(pady=(0, 20), padx=20, fill='x')
        
        self.status_label = ctk.CTkLabel(main_card, text="")
        self.status_label.pack(pady=(0, 20))

    def activate_license(self):
        key = self.key_entry.get().strip()
        if not key: return
        
        self.update_status("⏳ Активація...", "#FF9800")
        self.activate_button.configure(state="disabled")
        threading.Thread(target=self._activate_license_thread, args=(key,), daemon=True).start()

    def _activate_license_thread(self, license_key):
        try:
            response = requests.post(f"{SERVER_URL}/activate", json={"license_key": license_key, "hwid": self.hwid}, timeout=10)
            data = response.json()
            
            if response.status_code == 200 and data.get("success"):
                self.license_key = license_key
                self.is_activated = True
                self.activation_data = {"license_info": data}
                self.save_activation_state()
                self.root.after(0, lambda: self.update_status("✅ Ліцензія активована!", COLOR_ACCENT_GREEN))
                self.root.after(1000, self.show_main_screen)
            else:
                self.root.after(0, lambda: self.update_status(f"❌ {data.get('message', 'Помилка')}", COLOR_START_ACTIVE))
        except:
            self.root.after(0, lambda: self.update_status("❌ Помилка з'єднання", COLOR_START_ACTIVE))
        finally:
            self.root.after(0, lambda: self.activate_button.configure(state="normal"))

    def check_license_status(self):
        self.update_status("⏳ Перевірка...", "#FF9800")
        def _run():
            try:
                resp = requests.post(f"{SERVER_URL}/check_license", json={"license_key": self.license_key, "hwid": self.hwid})
                if resp.json().get("valid"):
                    self.root.after(0, lambda: self.update_status("✅ Активна", COLOR_ACCENT_GREEN))
                else:
                    self.root.after(0, lambda: self.update_status("❌ Недійсна", COLOR_START_ACTIVE))
            except:
                self.root.after(0, lambda: self.update_status("❌ Помилка", COLOR_START_ACTIVE))
        threading.Thread(target=_run, daemon=True).start()

    def deactivate_license(self):
        self.is_activated = False
        self.license_key = ""
        self.bot_downloaded = False
        
        # Видаляємо папку бота (опціонально)
        if os.path.exists(self.bot_dir):
            try: shutil.rmtree(self.bot_dir)
            except: pass
            
        # Видаляємо файл активації
        activation_file = os.path.join(self.launcher_dir, "activation.json")
        if os.path.exists(activation_file):
            try: os.remove(activation_file)
            except: pass
            
        self.show_activation_screen()

    def launch_bot(self):
        if not self.bot_downloaded:
            self.update_status("📥 Отримання посилання...", "#2196F3")
            self.launch_button.configure(state="disabled")
            threading.Thread(target=self.download_and_launch_bot, daemon=True).start()
        else:
            self.update_status("🚀 Запуск...", "#2196F3")
            self.launch_button.configure(state="disabled")
            threading.Thread(target=self._launch_bot_thread, daemon=True).start()

    def download_and_launch_bot(self):
        try:
            self.update_progress(10, "Авторизація...")
            
            # Отримання посилання від сервера
            response = requests.post(
                f"{SERVER_URL}/get_download_link",
                json={"license_key": self.license_key, "hwid": self.hwid},
                timeout=15
            )
            
            if response.status_code != 200:
                raise Exception(response.json().get("message", "Помилка сервера"))
            
            download_url = response.json().get("download_url")
            
            # Підготовка
            if os.path.exists(self.bot_dir): shutil.rmtree(self.bot_dir)
            
            zip_path = os.path.join(self.launcher_dir, "TIR_Bot_Full.zip")
            if os.path.exists(zip_path): os.remove(zip_path)

            # Завантаження
            self.update_progress(20, "Завантаження файлу...")
            with requests.get(download_url, stream=True) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(zip_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = 20 + (downloaded / total_size) * 50
                            mb = downloaded // 1024 // 1024
                            self.update_progress(progress, f"Завантаження: {mb}MB")

            # Розпаковка
            self.update_progress(75, "Розпаковка архіву...")
            if not zipfile.is_zipfile(zip_path):
                raise Exception("Файл пошкоджено")
                
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.launcher_dir)
            
            os.remove(zip_path)

            if not os.path.exists(self.bot_full_path):
                raise Exception("EXE файл не знайдено після розпаковки")

            self.bot_downloaded = True
            self.update_progress(100, "Завантаження завершено!")
            self.root.after(0, lambda: self.update_status("✅ Завантажено!", COLOR_ACCENT_GREEN))
            self.root.after(1000, self._launch_bot_thread)

        except Exception as e:
            self.root.after(0, lambda: self.update_status(f"❌ Помилка: {str(e)}", COLOR_START_ACTIVE))
            self.root.after(0, lambda: self.launch_button.configure(state="normal"))

    def _launch_bot_thread(self):
        try:
            # Перевіряємо драйвери тільки якщо вони ще не встановлені
            if not self.drivers_installed:
                self.update_status("🔧 Встановлення драйверів...", "#FF9800")
                if self._install_arduino_drivers():
                    self.drivers_installed = True
                    self.save_activation_state()
            
            self._run_bot_file(self.bot_executable)
            
        except Exception as e:
            self.root.after(0, lambda: self.update_status(f"❌ Error: {e}", COLOR_START_ACTIVE))
        finally:
            self.root.after(3000, lambda: self.launch_button.configure(state="normal"))

    def _install_arduino_drivers(self):
        try:
            if not os.path.exists(self.install_drivers_bat): return False
            process = subprocess.Popen(
                ['cmd.exe', '/c', self.install_drivers_bat],
                cwd=self.drivers_dir,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            process.communicate(timeout=60)
            return process.returncode == 0
        except: return False

    def _run_bot_file(self, bot_file):
        try:
            if not os.path.exists(self.bot_full_path): raise Exception("Файл не знайдено")
            subprocess.Popen([self.bot_full_path], creationflags=subprocess.CREATE_NO_WINDOW)
            self.root.after(0, lambda: self.update_status("✅ TIR Bot запущено!", COLOR_ACCENT_GREEN))
            return True
        except Exception as e:
            print(f"Error launching: {e}")
            return False

    def update_progress(self, value, text):
        if hasattr(self, 'progress_bar'):
            self.root.after(0, lambda: self.progress_bar.set(value/100))
            self.root.after(0, lambda: self.progress_label.configure(text=text))

    def update_status(self, message, color):
        if hasattr(self, 'status_label'):
            self.status_label.configure(text=message, text_color=color)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    launcher = TIRLauncher()
    launcher.run()
