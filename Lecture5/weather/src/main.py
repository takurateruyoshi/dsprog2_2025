import flet as ft
import requests
import json
from datetime import datetime

# --- 定数 ---
AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"
FORECAST_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/{}.json"

# グローバル変数として地域データを保持
try:
    AREA_RESPONSE = requests.get(AREA_URL, timeout=10)
    AREA_RESPONSE.raise_for_status()
    AREA_JSON = AREA_RESPONSE.json()
except requests.exceptions.RequestException as e:
    AREA_JSON = None
    print(f"起動エラー: 地域データの取得に失敗しました。{e}")

# --- 天気アイコンマッピング ---
def get_weather_icon(weather_text):
    """天気テキストから適切なアイコンと色を返す"""
    if "晴" in weather_text:
        if "曇" in weather_text or "くもり" in weather_text:
            return ft.Icons.WB_CLOUDY, ft.Colors.AMBER_600
        return ft.Icons.WB_SUNNY, ft.Colors.ORANGE_600
    elif "曇" in weather_text or "くもり" in weather_text:
        if "雨" in weather_text:
            return ft.Icons.CLOUD, ft.Colors.BLUE_GREY_600
        return ft.Icons.CLOUD, ft.Colors.GREY_600
    elif "雨" in weather_text:
        if "雷" in weather_text:
            return ft.Icons.THUNDERSTORM, ft.Colors.PURPLE_700
        return ft.Icons.UMBRELLA, ft.Colors.BLUE_700
    elif "雪" in weather_text:
        return ft.Icons.AC_UNIT, ft.Colors.LIGHT_BLUE_300
    elif "雷" in weather_text:
        return ft.Icons.FLASH_ON, ft.Colors.YELLOW_700
    else:
        return ft.Icons.QUESTION_MARK, ft.Colors.GREY_500

# --- 風向きアイコン ---
def get_wind_icon(wind_text):
    """風のテキストから方向アイコンを返す"""
    if "北" in wind_text:
        if "東" in wind_text:
            return ft.Icons.NORTH_EAST, "北東"
        elif "西" in wind_text:
            return ft.Icons.NORTH_WEST, "北西"
        else:
            return ft.Icons.NORTH, "北"
    elif "南" in wind_text:
        if "東" in wind_text:
            return ft.Icons.SOUTH_EAST, "南東"
        elif "西" in wind_text:
            return ft.Icons.SOUTH_WEST, "南西"
        else:
            return ft.Icons.SOUTH, "南"
    elif "東" in wind_text:
        return ft.Icons.EAST, "東"
    elif "西" in wind_text:
        return ft.Icons.WEST, "西"
    else:
        return ft.Icons.AIR, "風"

# --- メイン関数 ---
def main(page: ft.Page):
    page.title = "地方・都道府県連動 天気予報アプリ"
    page.padding = 20
    page.scroll = "adaptive"
    
    # 起動時のエラー処理
    if AREA_JSON is None:
        page.add(ft.Text("地域データのロードに失敗したため、アプリを起動できません。", color=ft.Colors.RED))
        page.update()
        return

    # 表示用コンテナ
    weather_content = ft.Column(
        [ft.Text("地方と都道府県を選択してください", size=16)],
        spacing=10
    )
    weather_container = ft.Container(
        content=weather_content,
        padding=15,
        border_radius=10,
        bgcolor=ft.Colors.BLUE_GREY_50,
        width=800
    )

    # 都道府県ドロップダウン
    office_dropdown = ft.Dropdown(
        label="都道府県",
        width=300,
        disabled=True,
        hint_text="地方を選択すると有効になります"
    )

    # 地方ドロップダウンのオプション作成
    center_options = []
    for code, info in AREA_JSON["centers"].items():
        center_options.append(
            ft.dropdown.Option(key=code, text=info["name"])
        )
    
    # --- ヘルパー関数 ---
    def format_date(iso_time_str):
        """ISO 8601形式の時間を 'MM/DD(曜日)' 形式に変換する"""
        try:
            dt = datetime.fromisoformat(iso_time_str)
            weekdays = ["月", "火", "水", "木", "金", "土", "日"]
            return dt.strftime(f"%m/%d({weekdays[dt.weekday()]})")
        except ValueError:
            return ""

    # 地方選択時のイベント
    def on_center_change(e):
        selected_center_code = e.control.value
        office_codes_in_center = AREA_JSON["centers"].get(selected_center_code, {}).get("children", [])
        new_office_options = []
        for office_code in office_codes_in_center:
            if office_code in AREA_JSON["offices"]:
                info = AREA_JSON["offices"][office_code]
                new_office_options.append(
                    ft.dropdown.Option(key=office_code, text=info["name"])
                )
        
        office_dropdown.options = new_office_options
        office_dropdown.value = None
        office_dropdown.disabled = False
        weather_content.controls = [
            ft.Text(f'{AREA_JSON["centers"][selected_center_code]["name"]} 内の都道府県を選択してください。', size=16)
        ]
        page.update()

    # 都道府県選択時のイベント
    def on_office_change(e):
        selected_office_code = e.control.value
        if not selected_office_code:
            return

        # ローディング表示
        weather_content.controls = [
            ft.ProgressRing(),
            ft.Text("天気データを取得中...", size=16)
        ]
        page.update()

        try:
            forecast_url = FORECAST_URL.format(selected_office_code)
            print(f"リクエストURL: {forecast_url}")
            
            forecast_response = requests.get(forecast_url, timeout=10)
            print(f"ステータスコード: {forecast_response.status_code}")
            
            forecast_response.raise_for_status()
            forecast_json = forecast_response.json()
            print(f"データ取得成功")
            
        except requests.exceptions.Timeout:
            weather_content.controls = [
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=50, color=ft.Colors.RED),
                ft.Text("タイムアウト: サーバーからの応答がありません。", color=ft.Colors.RED, size=16),
                ft.Text("しばらくしてから再度お試しください。", size=14)
            ]
            page.update()
            return
        except requests.exceptions.HTTPError as http_err:
            weather_content.controls = [
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=50, color=ft.Colors.RED),
                ft.Text(f"HTTPエラー: {http_err}", color=ft.Colors.RED, size=16),
                ft.Text(f"ステータスコード: {forecast_response.status_code}", size=14)
            ]
            page.update()
            return
        except requests.exceptions.RequestException as req_err:
            weather_content.controls = [
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=50, color=ft.Colors.RED),
                ft.Text(f"ネットワークエラー: {req_err}", color=ft.Colors.RED, size=16),
                ft.Text("インターネット接続を確認してください。", size=14)
            ]
            page.update()
            return
        
        try:
            office_name = AREA_JSON["offices"][selected_office_code]["name"]
            
            # --- 予報データの抽出 ---
            daily_forecast = forecast_json[0]["timeSeries"][0]
            daily_area = daily_forecast["areas"][0]
            
            time_defines_daily = daily_forecast["timeDefines"]
            weathers = daily_area["weathers"]
            winds = daily_area["winds"]
            waves = daily_area.get("waves", [""] * len(weathers))
            
            pop_forecast = forecast_json[0]["timeSeries"][1]
            pop_area = pop_forecast["areas"][0]
            
            time_defines_pop = pop_forecast["timeDefines"]
            pops = pop_area["pops"]
            
            temp_forecast = forecast_json[0]["timeSeries"][2]
            temp_area = temp_forecast["areas"][0]
            
            time_defines_temp = temp_forecast["timeDefines"]
            temps = temp_area["temps"]
            
            # --- 表示内容の組み立て ---
            new_controls = [
                ft.Text(f"📍 {office_name} の最新予報", size=24, weight="bold", color=ft.Colors.DEEP_PURPLE_700),
                ft.Divider(height=2, thickness=2),
            ]
            
            # 3日間の天気カード表示
            weather_cards = []
            for i in range(min(3, len(weathers))):
                date_label = format_date(time_defines_daily[i])
                
                day_name = ""
                if i == 0: day_name = "今日"
                elif i == 1: day_name = "明日"
                elif i == 2: day_name = "明後日"

                # 天気アイコン
                weather_icon, weather_color = get_weather_icon(weathers[i])
                
                # 風向きアイコン
                wind_icon, wind_dir = get_wind_icon(winds[i])
                
                # 波の情報
                wave_row = ft.Row([
                    ft.Icon(ft.Icons.WAVES, size=24, color=ft.Colors.WHITE70),
                    ft.Text(waves[i] if i < len(waves) and waves[i] else "情報なし", size=12, color=ft.Colors.WHITE70),
                ], alignment=ft.MainAxisAlignment.CENTER) if (i < len(waves) and waves[i]) else ft.Container(height=0)
                
                # カード作成
                card = ft.Container(
                    content=ft.Column([
                        ft.Text(day_name, size=18, weight="bold", color=ft.Colors.WHITE),
                        ft.Text(date_label, size=14, color=ft.Colors.WHITE70),
                        ft.Divider(height=1, color=ft.Colors.WHITE30),
                        ft.Icon(weather_icon, size=60, color=ft.Colors.WHITE),
                        ft.Text(weathers[i], size=14, color=ft.Colors.WHITE, text_align=ft.TextAlign.CENTER),
                        ft.Divider(height=1, color=ft.Colors.WHITE30),
                        ft.Row([
                            ft.Icon(wind_icon, size=24, color=ft.Colors.WHITE70),
                            ft.Text(winds[i], size=12, color=ft.Colors.WHITE70),
                        ], alignment=ft.MainAxisAlignment.CENTER),
                        wave_row,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    bgcolor=weather_color,
                    border_radius=15,
                    padding=20,
                    width=220,
                    shadow=ft.BoxShadow(
                        spread_radius=1,
                        blur_radius=15,
                        color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
                    )
                )
                weather_cards.append(card)
            
            new_controls.append(
                ft.Row(weather_cards, spacing=20, wrap=True)
            )
            
            new_controls.append(ft.Divider(height=20))
            
            # 気温表示
            if len(temps) >= 3:
                temp_container = ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.THERMOSTAT, size=40, color=ft.Colors.RED_400),
                        ft.Column([
                            ft.Text(f"今日（{format_date(time_defines_temp[0])}）午前9時頃: {temps[0]}°C", size=16),
                            ft.Text(f"明日（{format_date(time_defines_temp[2])}）予想最低気温: {temps[2]}°C", size=16),
                        ], spacing=5)
                    ], spacing=15),
                    bgcolor=ft.Colors.ORANGE_50,
                    border_radius=10,
                    padding=15,
                )
                new_controls.append(temp_container)
                new_controls.append(ft.Divider(height=20))
            
            # 降水確率
            pop_items = []
            for i in range(len(pops)):
                time_label = datetime.fromisoformat(time_defines_pop[i]).strftime("%H時")
                pop_value = int(pops[i]) if pops[i] else 0
                
                # 降水確率に応じて色を変更
                if pop_value >= 70:
                    pop_color = ft.Colors.RED_400
                elif pop_value >= 50:
                    pop_color = ft.Colors.ORANGE_400
                elif pop_value >= 30:
                    pop_color = ft.Colors.YELLOW_700
                else:
                    pop_color = ft.Colors.GREEN_400
                
                pop_items.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Text(time_label, size=12, color=ft.Colors.GREY_700),
                            ft.Icon(ft.Icons.WATER_DROP, size=30, color=pop_color),
                            ft.Text(f"{pops[i]}%", size=16, weight="bold", color=pop_color),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5),
                        bgcolor=ft.Colors.BLUE_50,
                        border_radius=10,
                        padding=15,
                        width=100,
                    )
                )
            
            new_controls.append(ft.Text("💧 時間別降水確率", size=18, weight="bold"))
            new_controls.append(ft.Row(pop_items, spacing=10, wrap=True))
            
            # 表示内容を更新
            weather_content.controls = new_controls

        except (KeyError, IndexError, Exception) as ex:
            print(f"解析エラー: {ex}")
            import traceback
            traceback.print_exc()
            weather_content.controls = [
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=50, color=ft.Colors.RED),
                ft.Text("天気情報の解析に失敗しました。", color=ft.Colors.RED, size=16),
                ft.Text(f"エラー詳細: {str(ex)}", size=12, color=ft.Colors.GREY_700)
            ]
            
        page.update()
        
    # 地方ドロップダウン
    center_dropdown = ft.Dropdown(
        label="地方",
        options=center_options,
        on_change=on_center_change,
        width=300,
        hint_text="地方を選択"
    )
    
    office_dropdown.on_change = on_office_change

    # 画面配置
    page.add(
        ft.Column(
            [
                ft.Text("🌤️ 天気予報アプリ", size=28, weight="bold", color=ft.Colors.BLUE_700),
                ft.Row([center_dropdown, office_dropdown], spacing=20),
                weather_container,
            ],
            spacing=20
        )
    )

ft.app(target=main)