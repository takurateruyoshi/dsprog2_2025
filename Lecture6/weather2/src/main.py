import flet as ft
import requests
import sqlite3
from datetime import datetime

# --- 定数 ---
DB_NAME = "weather_app.db"
AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"
FORECAST_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/{}.json"

# --- 天気コード辞書 (週間予報用) ---
WEATHER_CODE_MAP = {
    "100": "晴れ", "101": "晴時々曇", "110": "晴後時々曇", "111": "晴後曇",
    "200": "曇り", "201": "曇時々晴", "202": "曇一時雨", "203": "曇時々雨", "210": "曇後時々晴", "211": "曇後晴", "212": "曇後一時雨", "214": "曇後雨",
    "300": "雨", "301": "雨時々晴", "302": "雨時々止む", "303": "雨時々雪", "311": "雨後晴", "313": "雨後曇",
    "400": "雪", "401": "雪時々晴", "402": "雪時々止む", "403": "雪時々雨", "411": "雪後晴", "413": "雪後曇"
}

def get_weather_text_by_code(code):
    if code in WEATHER_CODE_MAP:
        return WEATHER_CODE_MAP[code]
    c = int(code)
    if 100 <= c < 200: return "晴れ系"
    if 200 <= c < 300: return "曇り系"
    if 300 <= c < 400: return "雨系"
    if 400 <= c < 500: return "雪系"
    return "不明"

# --- データベース管理クラス ---
class WeatherDatabase:
    def __init__(self, db_name):
        self.db_name = db_name
        self.init_db()

    def get_conn(self):
        return sqlite3.connect(self.db_name)

    def init_db(self):
        conn = self.get_conn()
        cur = conn.cursor()
        
        # テーブル初期化
        cur.execute("DROP TABLE IF EXISTS forecasts")
        
        # NOTE: area_codeとtarget_dateの複合主キーにしていますが、
        # 同じ地名でもコードが違うケース（API仕様）があるため、
        # 表示時に Python側で地名による重複排除を行います。
        sql_create_forecasts = """
        CREATE TABLE forecasts (
            area_code TEXT,
            parent_code TEXT,
            area_name TEXT,
            target_date TEXT,
            weather_code TEXT,
            weather_text TEXT,
            wind_text TEXT,
            wave_text TEXT,
            temps TEXT,
            pops TEXT,
            report_datetime TEXT,
            data_source TEXT,
            PRIMARY KEY (area_code, target_date)
        );
        """
        cur.execute(sql_create_forecasts)
        conn.commit()
        conn.close()

    def sync_all_data(self, json_data, parent_code):
        """週間予報と短期予報を同期"""
        # データ構造チェック
        if not isinstance(json_data, list):
            print("❌ データ形式エラー")
            return

        # 1. 週間予報 (Index 1)
        if len(json_data) > 1:
            self._sync_weekly_forecast(json_data[1], parent_code)
            
        # 2. 短期予報 (Index 0) - こちらを後から処理してUPDATE等も可能だが
        #    主キー(area_code)が異なる場合があるので、INSERT自体は両方行われる可能性がある。
        self._sync_short_forecast(json_data[0], parent_code)

    def _sync_weekly_forecast(self, data, parent_code):
        conn = self.get_conn()
        cur = conn.cursor()
        try:
            report_datetime = data['reportDatetime']
            ts_weather = data['timeSeries'][0]
            time_defines = ts_weather['timeDefines']
            
            ts_temps = data['timeSeries'][1] if len(data['timeSeries']) > 1 else None
            
            for area_idx, area in enumerate(ts_weather['areas']):
                a_code = area['area']['code']
                a_name = area['area']['name']
                
                temp_area = ts_temps['areas'][area_idx] if ts_temps else None

                for i, t_str in enumerate(time_defines):
                    dt = datetime.fromisoformat(t_str)
                    target_date = dt.strftime('%Y-%m-%d')
                    
                    w_code = area['weatherCodes'][i]
                    w_text = get_weather_text_by_code(w_code)
                    
                    pop_val = area['pops'][i] if 'pops' in area and area['pops'][i] else ""
                    pops_str = f"一日:{pop_val}%" if pop_val else ""
                    
                    temps_list = []
                    if temp_area:
                        # 週間予報の気温(Min/Max)
                        try:
                            min_t = temp_area['tempsMin'][i]
                            max_t = temp_area['tempsMax'][i]
                            if min_t and min_t.strip(): temps_list.append(min_t)
                            if max_t and max_t.strip(): temps_list.append(max_t)
                        except IndexError:
                            pass # データ不足時はスキップ
                    
                    temps_str = ",".join(temps_list)

                    cur.execute("""
                        INSERT OR REPLACE INTO forecasts 
                        (area_code, parent_code, area_name, target_date, 
                         weather_code, weather_text, wind_text, wave_text, 
                         temps, pops, report_datetime, data_source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'weekly')
                    """, (
                        a_code, parent_code, a_name, target_date,
                        w_code, w_text, "", "",
                        temps_str, pops_str, report_datetime
                    ))
            conn.commit()
        except Exception as e:
            print(f"⚠️ 週間予報処理エラー: {e}")
        finally:
            conn.close()

    def _sync_short_forecast(self, data, parent_code):
        conn = self.get_conn()
        cur = conn.cursor()
        try:
            report_datetime = data['reportDatetime']
            ts_weather = data['timeSeries'][0]
            time_defines_weather = ts_weather['timeDefines']
            
            ts_temps = data['timeSeries'][2] if len(data['timeSeries']) > 2 else None
            time_defines_temps = ts_temps['timeDefines'] if ts_temps else []

            ts_pops = data['timeSeries'][1] if len(data['timeSeries']) > 1 else None
            time_defines_pops = ts_pops['timeDefines'] if ts_pops else []

            for area_idx, area_data in enumerate(ts_weather['areas']):
                a_code = area_data['area']['code']
                a_name = area_data['area']['name']
                
                for time_idx, t_str in enumerate(time_defines_weather):
                    dt = datetime.fromisoformat(t_str)
                    target_date = dt.strftime('%Y-%m-%d')
                    
                    w_code = area_data['weatherCodes'][time_idx]
                    w_text = area_data['weathers'][time_idx]
                    wind_text = area_data['winds'][time_idx]
                    wave_text = area_data['waves'][time_idx] if 'waves' in area_data and time_idx < len(area_data['waves']) else ""

                    # 気温
                    temps_list = []
                    if ts_temps and area_idx < len(ts_temps['areas']):
                        temp_area = ts_temps['areas'][area_idx]
                        for t_idx, t_time in enumerate(time_defines_temps):
                            if t_time.startswith(target_date):
                                val = temp_area['temps'][t_idx]
                                if val and val.strip(): temps_list.append(val)

                    # 降水確率
                    pops_list = []
                    if ts_pops and area_idx < len(ts_pops['areas']):
                        pop_area = ts_pops['areas'][area_idx]
                        for p_idx, p_time in enumerate(time_defines_pops):
                            if p_time.startswith(target_date):
                                val = pop_area['pops'][p_idx]
                                hh = datetime.fromisoformat(p_time).strftime("%H")
                                if val and val.strip(): pops_list.append(f"{hh}時:{val}%")

                    temps_str = ",".join(temps_list)
                    pops_str = ",".join(pops_list)
                    
                    cur.execute("""
                        INSERT OR REPLACE INTO forecasts 
                        (area_code, parent_code, area_name, target_date, 
                         weather_code, weather_text, wind_text, wave_text, 
                         temps, pops, report_datetime, data_source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'short')
                    """, (
                        a_code, parent_code, a_name, target_date,
                        w_code, w_text, wind_text, wave_text,
                        temps_str, pops_str, report_datetime
                    ))
            conn.commit()
        except Exception as e:
            print(f"❌ 短期予報処理エラー: {e}")
        finally:
            conn.close()

    def get_available_dates(self, parent_code):
        conn = self.get_conn()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT target_date FROM forecasts WHERE parent_code = ? ORDER BY target_date", (parent_code,))
        dates = [row[0] for row in cur.fetchall()]
        conn.close()
        return dates

    def get_forecasts_by_date(self, parent_code, target_date):
        conn = self.get_conn()
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # まず対象の日付の全データを取得
        cur.execute("SELECT * FROM forecasts WHERE parent_code = ? AND target_date = ?", (parent_code, target_date))
        rows = cur.fetchall()
        conn.close()
        
        # --- 重複排除ロジック (Python側で処理) ---
        # 同じエリア名(area_name)で、data_sourceが異なる場合、'short'を優先する
        unique_data = {}
        
        for row in rows:
            name = row['area_name']
            source = row['data_source']
            
            if name not in unique_data:
                # まだ登録されていなければ追加
                unique_data[name] = row
            else:
                # 既に登録済みの場合、現在持っているのがweeklyで、新しいのがshortなら上書き
                existing_source = unique_data[name]['data_source']
                if existing_source == 'weekly' and source == 'short':
                    unique_data[name] = row
                # それ以外（既にshortがある、または同等）なら何もしない

        return list(unique_data.values())

# --- UIヘルパー ---
def get_weather_icon(weather_text, weather_code):
    text = weather_text if weather_text else ""
    if "晴" in text: return (ft.Icons.WB_SUNNY, ft.Colors.ORANGE_600) if "曇" not in text else (ft.Icons.WB_CLOUDY, ft.Colors.AMBER_600)
    if "雨" in text: return (ft.Icons.UMBRELLA, ft.Colors.BLUE_700)
    if "雪" in text: return (ft.Icons.AC_UNIT, ft.Colors.LIGHT_BLUE_300)
    if "曇" in text: return (ft.Icons.CLOUD, ft.Colors.GREY_600)
    
    c = int(weather_code)
    if 100 <= c < 200: return (ft.Icons.WB_SUNNY, ft.Colors.ORANGE_600)
    if 200 <= c < 300: return (ft.Icons.CLOUD, ft.Colors.GREY_600)
    if 300 <= c < 400: return (ft.Icons.UMBRELLA, ft.Colors.BLUE_700)
    if 400 <= c < 500: return (ft.Icons.AC_UNIT, ft.Colors.LIGHT_BLUE_300)
    
    return (ft.Icons.QUESTION_MARK, ft.Colors.GREY)

try:
    AREA_JSON = requests.get(AREA_URL).json()
except:
    AREA_JSON = None

# --- メインアプリ ---
def main(page: ft.Page):
    page.title = "週間天気対応 DBアプリ"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.scroll = "adaptive"

    if not AREA_JSON:
        page.add(ft.Text("ネットワークエラー: 地域情報を取得できません"))
        return

    db = WeatherDatabase(DB_NAME)

    center_dd = ft.Dropdown(label="地方", width=200, options=[ft.dropdown.Option(k, v["name"]) for k, v in AREA_JSON["centers"].items()])
    office_dd = ft.Dropdown(label="都道府県", width=200, disabled=True)
    date_dd = ft.Dropdown(label="日付を選択", width=300, disabled=True, icon=ft.Icons.CALENDAR_MONTH)
    result_col = ft.Column(spacing=20)
    status_txt = ft.Text("地域を選択してください", color="grey")

    def create_detail_card(row):
        w_text = row['weather_text']
        w_code = row['weather_code']
        wind = row['wind_text']
        wave = row['wave_text']
        temps_str_list = row['temps'].split(',') if row['temps'] else []
        pops_raw = row['pops'].split(',') if row['pops'] else []

        icon, color = get_weather_icon(w_text, w_code)
        
        # 気温表示ロジック
        temp_controls = []
        if temps_str_list:
            try:
                temps_int = sorted([int(t) for t in temps_str_list])
                if len(temps_int) >= 2 and temps_int[0] != temps_int[-1]:
                    min_t, max_t = temps_int[0], temps_int[-1]
                    temp_controls.append(ft.Container(
                        content=ft.Row([
                            ft.Column([ft.Text("最低", size=10, color="blue"), ft.Text(f"{min_t}℃", size=16, weight="bold", color=ft.Colors.BLUE_700)], spacing=0, horizontal_alignment="center"),
                            ft.Text("/", size=20, color="grey"),
                            ft.Column([ft.Text("最高", size=10, color="red"), ft.Text(f"{max_t}℃", size=16, weight="bold", color=ft.Colors.RED_700)], spacing=0, horizontal_alignment="center"),
                        ], alignment="center", spacing=15),
                        bgcolor=ft.Colors.WHITE, padding=10, border_radius=8
                    ))
                else:
                    val = temps_int[0] if temps_int else "-"
                    temp_controls.append(ft.Container(
                        content=ft.Row([ft.Icon(ft.Icons.THERMOSTAT, size=16, color="orange"), ft.Text("予想気温:", size=12, color="grey"), ft.Text(f"{val}℃", size=16, weight="bold", color=ft.Colors.ORANGE_800)], alignment="center"),
                        bgcolor=ft.Colors.WHITE, padding=10, border_radius=8
                    ))
            except ValueError: pass

        # 降水確率
        pop_controls = []
        if pops_raw:
            pop_items = [ft.Container(content=ft.Text(p, size=10, color="black"), bgcolor=ft.Colors.WHITE, padding=4, border_radius=4) for p in pops_raw]
            pop_controls.append(ft.Text("降水確率:", size=12, color="white70"))
            pop_controls.append(ft.Row(pop_items, wrap=True, spacing=4))

        # 風・波
        wind_row = ft.Container()
        if wind: wind_row = ft.Row([ft.Icon(ft.Icons.AIR, size=14, color="white70"), ft.Text(wind, size=12, color="white70", expand=True)])
        wave_row = ft.Container()
        if wave: wave_row = ft.Row([ft.Icon(ft.Icons.WAVES, size=16, color="white70"), ft.Text(f"{wave}", size=12, color="white70", expand=True)])

        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.LOCATION_ON, color="white", size=18), ft.Text(row['area_name'], size=18, weight="bold", color="white")]),
                ft.Divider(color="white30", height=5),
                ft.Row([ft.Icon(icon, size=48, color="white"), ft.Container(content=ft.Text(w_text, size=14, color="white", weight="bold"), expand=True)], alignment="start"),
                wind_row, wave_row,
                ft.Divider(color="white30", height=5),
                ft.Column(temp_controls + pop_controls, spacing=8)
            ], spacing=5),
            bgcolor=color, border_radius=15, padding=20, width=320, shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.with_opacity(0.3, ft.Colors.BLACK))
        )

    def show_forecasts(target_date):
        # 修正されたデータ取得メソッドを使用
        rows = db.get_forecasts_by_date(office_dd.value, target_date)
        result_col.controls.clear()
        
        if not rows:
            result_col.controls.append(ft.Text("データが見つかりません"))
            page.update()
            return

        dt = datetime.strptime(target_date, '%Y-%m-%d')
        date_str = dt.strftime("%m月%d日")
        
        # タイトルの作成
        result_col.controls.append(ft.Text(f"📅 {date_str} の天気", size=20, weight="bold"))
        
        cards = [create_detail_card(row) for row in rows]
        result_col.controls.append(ft.Row(cards, wrap=True, alignment="center"))
        
        last = rows[0]['report_datetime']
        last_dt = datetime.fromisoformat(last).strftime("%Y/%m/%d %H:%M")
        result_col.controls.append(ft.Text(f"更新: {last_dt}", size=12, color="grey", text_align="right"))
        page.update()

    def on_office_change(e):
        if not office_dd.value: return
        status_txt.value = "データを取得・更新中..."
        date_dd.disabled = True
        result_col.controls.clear()
        page.update()

        try:
            res = requests.get(FORECAST_URL.format(office_dd.value))
            res.raise_for_status()
            db.sync_all_data(res.json(), office_dd.value)
            
            dates = db.get_available_dates(office_dd.value)
            if dates:
                date_dd.options = [ft.dropdown.Option(d) for d in dates]
                date_dd.value = dates[0]
                date_dd.disabled = False
                status_txt.value = "日付を選択してください"
                show_forecasts(dates[0])
            else:
                status_txt.value = "データなし"
        except Exception as ex:
            status_txt.value = f"エラー: {ex}"
            print(ex)
        page.update()

    def on_center_change(e):
        children = AREA_JSON["centers"].get(center_dd.value, {}).get("children", [])
        office_dd.options = [ft.dropdown.Option(c, AREA_JSON["offices"][c]["name"]) for c in children if c in AREA_JSON["offices"]]
        office_dd.value = None
        office_dd.disabled = False
        page.update()

    center_dd.on_change = on_center_change
    office_dd.on_change = on_office_change
    date_dd.on_change = lambda e: show_forecasts(date_dd.value)

    page.add(
        ft.Text("🌤️ 週間天気DBアプリ", size=28, weight="bold"),
        ft.Container(content=ft.Column([ft.Row([center_dd, office_dd]), ft.Row([ft.Icon(ft.Icons.HISTORY), date_dd]), status_txt]), padding=15, bgcolor=ft.Colors.BLUE_50, border_radius=10),
        ft.Divider(),
        result_col
    )

if __name__ == "__main__":
    ft.app(target=main)