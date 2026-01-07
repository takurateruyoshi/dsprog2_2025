import flet as ft
import requests
from datetime import datetime
import sqlite3
import os

# --- 定数 ---
AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"
FORECAST_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/{}.json"

# --- DB関数 (改良版) ---
def db(sql, params=()):
    
    path = ''
    db_name = 'region.db'

    try:
        conn = sqlite3.connect(path + db_name)
        cur = conn.cursor()
        
        cur.execute(sql, params)
        
        # SELECT文かどうかを判定して処理を分岐
        if sql.strip().upper().startswith("SELECT"):
            data = cur.fetchall()
            return data
        else:
            conn.commit()
            return None

    except sqlite3.Error as e:
        print('SQLite error:', e)
         
    finally:
        # DBへの接続を閉じる
        conn.close()
    
    

    try:
        #DBへのコネクションを確立
        conn = sqlite3.connect(path + db_name)

        #SQL(ROBを操作するための言語)を実行するためのカーソルオブジェクトを取得
        cur = conn.cursor()

        # SQL文の作成
        # テーブルの作成
        sql = "CREATE TABLE cars (id int, name TEXT, price INTEGER);"

        # SQL文の実行
        cur.execute(sql)

        conn.commit()  # 変更を保存

    except sqlite3.Error as e:
        print('SQLite error:', e)
        
    finally:
        # DBへの接続を閉じる
        conn.close()

# --- データ管理ロジック ---

def init_tables():
    # 地方テーブル
    sql_centers = """
    CREATE TABLE IF NOT EXISTS centers (
        code TEXT PRIMARY KEY,
        name TEXT,
        enName TEXT,
        officeName TEXT
    );
    """
    db(sql_centers)

    # 都道府県（予報区）テーブル
    # parent_center_code で地方と紐づける
    sql_offices = """
    CREATE TABLE IF NOT EXISTS offices (
        code TEXT PRIMARY KEY,
        name TEXT,
        enName TEXT,
        officeName TEXT,
        parent_center_code TEXT
    );
    """
    db(sql_offices)

def load_area_data():
    """
    1. DBをチェック
    2. 空ならAPIから取得してDBに保存
    3. DBからデータを読み込んで、アプリ用の辞書形式(JSON構造)で返す
    """
    init_tables()
    
    # DBにデータがあるか確認
    check_data = db("SELECT count(*) FROM centers")
    
    # データがない場合（初回起動時など）はAPIから取得して保存
    if check_data and check_data[0][0] == 0:
        print("DBにデータがありません。APIから取得して保存します...")
        try:
            response = requests.get(AREA_URL, timeout=10)
            response.raise_for_status()
            area_json = response.json()
            
            # centers (地方) の保存
            for code, info in area_json["centers"].items():
                db("INSERT INTO centers (code, name, enName, officeName) VALUES (?, ?, ?, ?)", 
                   (code, info["name"], info["enName"], info["officeName"]))
                
                # centersの中にある children (都道府県コード) を使って紐付け情報を保存したいが、
                # officesデータ自体は別キーにあるため、まずはcentersを保存。
                # 紐付けのために children リストを一時的に覚えておく必要はない（offices側で処理）
            
            # offices (都道府県) の保存
            # 注意: APIの構造上、どのofficeがどのcenterに属するかは center.children に入っている
            # そのため、先にcenterを回して親子関係を特定する
            parent_map = {} # office_code -> center_code
            for center_code, center_info in area_json["centers"].items():
                for child_code in center_info["children"]:
                    parent_map[child_code] = center_code
            
            for code, info in area_json["offices"].items():
                parent_code = parent_map.get(code, "")
                db("INSERT INTO offices (code, name, enName, officeName, parent_center_code) VALUES (?, ?, ?, ?, ?)",
                   (code, info["name"], info["enName"], info["officeName"], parent_code))
                
            print("DBへの保存が完了しました。")
            
        except Exception as e:
            print(f"データ初期化エラー: {e}")
            return None

    # --- DBからデータを読み込んでアプリ用の構造(JSON互換)に復元する ---
    print("DBからデータを読み込み中...")
    
    centers_data = {}
    offices_data = {}
    
    # 地方データの取得
    rows_centers = db("SELECT code, name, enName, officeName FROM centers")
    if rows_centers:
        for row in rows_centers:
            code, name, enName, officeName = row
            # childrenは後でofficesを見て埋める
            centers_data[code] = {
                "name": name, 
                "enName": enName, 
                "officeName": officeName, 
                "children": []
            }
            
    # 都道府県データの取得
    rows_offices = db("SELECT code, name, enName, officeName, parent_center_code FROM offices")
    if rows_offices:
        for row in rows_offices:
            code, name, enName, officeName, parent_code = row
            offices_data[code] = {
                "name": name,
                "enName": enName,
                "officeName": officeName
            }
            # 親（地方）のchildrenリストに追加
            if parent_code in centers_data:
                centers_data[parent_code]["children"].append(code)
    
    return {"centers": centers_data, "offices": offices_data}


# --- 天気アイコンマッピング (変更なし) ---
def get_weather_icon(weather_text):
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

# --- 風向きアイコン (変更なし) ---
def get_wind_icon(wind_text):
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
    page.title = "地方・都道府県連動 天気予報アプリ (SQL版)"
    page.padding = 20
    page.scroll = "adaptive"
    
    # アプリ起動時にデータをロード (DB or API)
    AREA_JSON = load_area_data()
    
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
    # 辞書順だとバラバラになる可能性があるため、コード順にソートして表示
    sorted_centers = sorted(AREA_JSON["centers"].items(), key=lambda x: x[0])
    
    for code, info in sorted_centers:
        center_options.append(
            ft.dropdown.Option(key=code, text=info["name"])
        )
    
    # --- ヘルパー関数 ---
    def format_date(iso_time_str):
        try:
            dt = datetime.fromisoformat(iso_time_str)
            weekdays = ["月", "火", "水", "木", "金", "土", "日"]
            return dt.strftime(f"%m/%d({weekdays[dt.weekday()]})")
        except ValueError:
            return ""

    # 地方選択時のイベント
    def on_center_change(e):
        selected_center_code = e.control.value
        if not selected_center_code:
            return
            
        office_codes_in_center = AREA_JSON["centers"].get(selected_center_code, {}).get("children", [])
        new_office_options = []
        
        # 都道府県もコード順などでソートしたほうが綺麗だが、ここではリスト順
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

    # 都道府県選択時のイベント (予報取得ロジックは変更なし)
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
            # print(f"リクエストURL: {forecast_url}")
            
            forecast_response = requests.get(forecast_url, timeout=10)
            forecast_response.raise_for_status()
            forecast_json = forecast_response.json()
            
        except Exception as req_err:
            weather_content.controls = [
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=50, color=ft.Colors.RED),
                ft.Text(f"予報データの取得に失敗しました", color=ft.Colors.RED, size=16),
                ft.Text(f"{req_err}", size=14)
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

                weather_icon, weather_color = get_weather_icon(weathers[i])
                wind_icon, wind_dir = get_wind_icon(winds[i])
                
                wave_row = ft.Row([
                    ft.Icon(ft.Icons.WAVES, size=24, color=ft.Colors.WHITE70),
                    ft.Text(waves[i] if i < len(waves) and waves[i] else "情報なし", size=12, color=ft.Colors.WHITE70),
                ], alignment=ft.MainAxisAlignment.CENTER) if (i < len(waves) and waves[i]) else ft.Container(height=0)
                
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
                    shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK))
                )
                weather_cards.append(card)
            
            new_controls.append(ft.Row(weather_cards, spacing=20, wrap=True))
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
                
                if pop_value >= 70: pop_color = ft.Colors.RED_400
                elif pop_value >= 50: pop_color = ft.Colors.ORANGE_400
                elif pop_value >= 30: pop_color = ft.Colors.YELLOW_700
                else: pop_color = ft.Colors.GREEN_400
                
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
            
            weather_content.controls = new_controls

        except Exception as ex:
            print(f"解析エラー: {ex}")
            weather_content.controls = [
                ft.Text("天気情報の解析に失敗しました。", color=ft.Colors.RED)
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