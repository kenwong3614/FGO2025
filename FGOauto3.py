import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter.font as tkfont
import pyautogui
import time
import threading
import os
from PIL import Image, ImageGrab, ImageTk
import json

try:
    import keyboard
except ImportError:
    print("建議 pip install keyboard 以支援 Esc 熱鍵停止")

pyautogui.FAILSAFE = True

class AutoBotUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FGO自動化助手 - 姐姐專屬版 (修正版)")
        self.root.geometry("700x800")
        
        self.actions = []
        self.is_running = False
        self.confidence = 0.8
        self.dragging_idx = None
        
        # --- 介面佈局 ---
        
        # 1. 清單框架
        listbox_frame = tk.Frame(root)
        listbox_frame.pack(pady=10, fill=tk.BOTH, expand=True, padx=10)
        
        # 2. 行號 Canvas (左側灰色條)
        self.number_canvas = tk.Canvas(listbox_frame, width=40, bg="#e0e0e0", highlightthickness=0)
        self.number_canvas.pack(side=tk.LEFT, fill=tk.Y)
        
        # 3. 動作清單 Listbox (右側白色區)
        self.listbox = tk.Listbox(listbox_frame, selectmode=tk.SINGLE, height=18, font=("Consolas", 10))
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # --- 滾動條同步綁定 ---
        # 當滑鼠在 Listbox 滾動時
        self.listbox.bind("<MouseWheel>", self.sync_scroll)
        self.listbox.bind("<Button-4>", lambda e: self.sync_scroll(e, -1))
        self.listbox.bind("<Button-5>", lambda e: self.sync_scroll(e, 1))

        # 當滑鼠在 行號區 滾動時
        self.number_canvas.bind("<MouseWheel>", self.sync_scroll_canvas)
        self.number_canvas.bind("<Button-4>", lambda e: self.sync_scroll_canvas(e, -1))
        self.number_canvas.bind("<Button-5>", lambda e: self.sync_scroll_canvas(e, 1))
        
        # --- 拖曳排序綁定 ---
        self.drag_data = {"index": None, "y": 0, "item": None}
        self.listbox.bind("<Button-1>", self.on_drag_start)
        self.listbox.bind("<B1-Motion>", self.on_drag_motion)
        self.listbox.bind("<ButtonRelease-1>", self.on_drag_release)
        self.listbox.bind("<Double-1>", self.edit_action)
        
        # --- 按鈕區 ---
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="截取目標圖片", command=self.capture_image_tool, bg="#add8e6").grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="新增: 點擊圖片", command=self.add_click_image_action).grid(row=0, column=1, padx=5)
        tk.Button(btn_frame, text="新增: 雙擊圖片", command=self.add_double_click_action).grid(row=0, column=2, padx=5)
        tk.Button(btn_frame, text="新增: 等待秒數", command=self.add_wait_action).grid(row=0, column=3, padx=5)
        tk.Button(btn_frame, text="新增: 滾輪向下", command=self.add_scroll_down_action).grid(row=0, column=4, padx=5)
        tk.Button(btn_frame, text="新增: 條件跳轉", command=self.add_conditional_action).grid(row=0, column=5, padx=5)
        
        # --- 編輯區 ---
        edit_frame = tk.Frame(root)
        edit_frame.pack(pady=5)
        tk.Button(edit_frame, text="刪除選取", command=self.delete_action, bg="#ffcccb").pack(side=tk.LEFT, padx=5)
        tk.Button(edit_frame, text="清除所有", command=self.clear_all).pack(side=tk.LEFT, padx=5)
        tk.Button(edit_frame, text="測試選取動作", command=self.test_action).pack(side=tk.LEFT, padx=5)
        tk.Button(edit_frame, text="儲存腳本", command=self.save_script).pack(side=tk.LEFT, padx=5)
        tk.Button(edit_frame, text="載入腳本", command=self.load_script).pack(side=tk.LEFT, padx=5)
        
        # --- 設定區 ---
        conf_frame = tk.Frame(root)
        conf_frame.pack(pady=5)
        tk.Label(conf_frame, text="相似度門檻:").pack(side=tk.LEFT)
        self.conf_slider = tk.Scale(conf_frame, from_=0.6, to=0.95, resolution=0.05, orient=tk.HORIZONTAL, command=self.update_confidence)
        self.conf_slider.set(0.8)
        self.conf_slider.pack(side=tk.LEFT, padx=10)
        
        # --- 執行區 ---
        run_frame = tk.Frame(root)
        run_frame.pack(pady=20)
        self.loop_var = tk.BooleanVar(value=True)
        tk.Checkbutton(run_frame, text="無限重複刷本", variable=self.loop_var).pack(side=tk.LEFT)
        tk.Button(run_frame, text="▶ 開始執行", command=self.start_thread, bg="#90ee90", width=15, height=2).pack(side=tk.LEFT, padx=20)
        tk.Button(run_frame, text="⏹ 停止", command=self.stop_bot, bg="#ff6961", width=10).pack(side=tk.LEFT)
        
        self.progress = ttk.Progressbar(root, length=500, mode="determinate")
        self.progress.pack(pady=10)
        
        self.status_label = tk.Label(root, text="就緒，姐姐在等你喔～", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        keyboard.add_hotkey('esc', self.stop_bot)
        
        if not os.path.exists("targets"):
            os.makedirs("targets")
        
        self.refresh_listbox()
    
    def log(self, message):
        self.status_label.config(text=message)
        self.root.update_idletasks()
    
    def update_confidence(self, value):
        self.confidence = float(value)
        self.log(f"相似度門檻調整為 {value}")
    
    def refresh_listbox(self):
        """ 刷新介面與行號的核心邏輯 """
        self.listbox.delete(0, tk.END)
        self.number_canvas.delete("all")
        
        # 取得目前字體的高度 (像素)
        font = self.listbox.cget("font")
        font_obj = tkfont.Font(font=font)
        line_height = font_obj.metrics("linespace")
        
        # 設定 Canvas 滾動的單位像素等於一行的高度 (這讓對齊更精準)
        self.number_canvas.config(yscrollincrement=line_height)
        
        y = 0
        for i, action in enumerate(self.actions):
            display = self.get_action_display_text(action)
            self.listbox.insert(tk.END, display)
            
            # 在 Canvas 上畫出行號，垂直置中
            self.number_canvas.create_text(
                20, y + line_height // 2, 
                text=str(i+1), 
                anchor="center", 
                font=("Consolas", 10, "bold"), 
                fill="#555555"
            )
            y += line_height
            
        # 即使清單是空的，也畫出一些灰色的空行號，比較好看
        if len(self.actions) < 15:
            for i in range(len(self.actions), 15):
                self.number_canvas.create_text(
                    20, y + line_height // 2, 
                    text=str(i+1), 
                    anchor="center", 
                    font=("Consolas", 10), 
                    fill="#cccccc"
                )
                y += line_height

        # 設定滾動區域
        self.number_canvas.config(scrollregion=(0, 0, 50, y))
    
    def sync_scroll(self, event):
        delta = (event.delta // 120) * -1 if event.delta else 0
        self.number_canvas.yview_scroll(delta, "units")
    
    def sync_scroll_canvas(self, event):
        delta = (event.delta // 120) * -1 if event.delta else 0
        self.listbox.yview_scroll(delta, "units")
    
    def get_action_display_text(self, action):
        if action["type"] == "wait":
            return f"等待 {action['data']} 秒"
        elif action["type"] == "scroll_down":
            return f"滾輪向下 {action['data']} 次"
        elif action["type"] == "conditional":
            image_name = os.path.basename(action.get('image', '未知圖片'))
            attempts_desc = "無限" if action.get('max_attempts', 1) < 0 else action.get('max_attempts', 1)
            found_desc = f"執行 {len(action.get('found_actions', []))} 個動作"
            not_found_desc = f"執行 {len(action.get('not_found_actions', []))} 個動作"
            return f"條件 ({attempts_desc} 次): {image_name} → 找到: {found_desc} | 沒找到: {not_found_desc}"
        else:
            return f"{action['type'].capitalize()}: {os.path.basename(action['data'])}"

    def add_click_image_action(self):
        file_path = filedialog.askopenfilename(initialdir="targets", filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if file_path:
            sel = self.listbox.curselection()
            insert_idx = len(self.actions) if not sel else sel[0] + 1
            self.actions.insert(insert_idx, {"type": "click", "data": file_path})
            self.refresh_listbox()
    
    def add_double_click_action(self):
        file_path = filedialog.askopenfilename(initialdir="targets", filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if file_path:
            sel = self.listbox.curselection()
            insert_idx = len(self.actions) if not sel else sel[0] + 1
            self.actions.insert(insert_idx, {"type": "double_click", "data": file_path})
            self.refresh_listbox()
    
    def add_wait_action(self):
        sec = simpledialog.askfloat("等待時間", "輸入秒數（可小數）", minvalue=0.1)
        if sec:
            sel = self.listbox.curselection()
            insert_idx = len(self.actions) if not sel else sel[0] + 1
            self.actions.insert(insert_idx, {"type": "wait", "data": sec})
            self.refresh_listbox()
    
    def add_scroll_down_action(self):
        amount = simpledialog.askinteger("滾輪向下", "輸入滾輪向下次數（1次約120單位）", minvalue=1, initialvalue=1)
        if amount:
            sel = self.listbox.curselection()
            insert_idx = len(self.actions) if not sel else sel[0] + 1
            self.actions.insert(insert_idx, {"type": "scroll_down", "data": amount})
            self.refresh_listbox()
    
    def add_conditional_action(self):
        file_path = filedialog.askopenfilename(initialdir="targets", title="選擇條件圖片", filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if not file_path: return
        
        loop_choice = messagebox.askyesnocancel("循環模式", "是：直到找到為止\n否：檢查指定次數\n取消：只檢查一次")
        if loop_choice is None: return
        
        max_attempts = 1
        if loop_choice:
            max_attempts = -1  # 無限直到找到
        elif loop_choice is False:
            attempts = simpledialog.askinteger("檢查次數", "最多檢查幾次？（1~99）", minvalue=1, maxvalue=99)
            if attempts is None: return
            max_attempts = attempts
        
        # 記住插入位置
        sel = self.listbox.curselection()
        self.insert_idx = len(self.actions) if not sel else sel[0] + 1
        
        # 備份主動作
        self.backup_actions = self.actions.copy()
        
        # 清空actions，變成臨時收集「找到時」子動作
        self.actions = []
        self.refresh_listbox()
        
        self.temp_image = file_path
        self.temp_max_attempts = max_attempts
        
        self.log("開始新增【找到圖片時】的子動作（完成後按「完成找到時動作」）")
        self.found_complete_btn = tk.Button(self.root, text="完成找到時動作 → 開始沒找到時", command=self.complete_found_temp, bg="#90ee90")
        self.found_complete_btn.pack(pady=5)
    
    def complete_found_temp(self):
        self.temp_found_actions = self.actions.copy()
        # 清空actions，準備收集「沒找到時」子動作
        self.actions = []
        self.refresh_listbox()
        self.found_complete_btn.pack_forget()
        
        self.log("「找到時」子動作已保存。現在開始新增【沒找到圖片時】的子動作（完成後按「完成條件設定」）")
        self.not_found_complete_btn = tk.Button(self.root, text="完成條件設定", command=self.complete_not_found_temp, bg="#ff9800")
        self.not_found_complete_btn.pack(pady=5)
    
    def complete_not_found_temp(self):
        self.temp_not_found_actions = self.actions.copy()
        self.not_found_complete_btn.pack_forget()
        
        # 恢復主動作清單
        self.actions = self.backup_actions
        
        # 打包條件動作
        conditional = {
            "type": "conditional",
            "image": self.temp_image,
            "max_attempts": self.temp_max_attempts,
            "found_actions": self.temp_found_actions,
            "not_found_actions": self.temp_not_found_actions
        }
        
        # 插入到原本位置
        self.actions.insert(self.insert_idx, conditional)
        self.refresh_listbox()
        self.log("條件區塊新增完成！雙擊可查看子動作")
    
    def delete_action(self):
        sel = self.listbox.curselection()
        if sel:
            idx = sel[0]
            self.actions.pop(idx)
            self.refresh_listbox()
    
    def clear_all(self):
        self.actions.clear()
        self.refresh_listbox()
    
    def load_script(self):
        file = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if file:
            with open(file, "r", encoding="utf-8") as f:
                self.actions = json.load(f)
            self.refresh_listbox()
            self.log("腳本已載入")
    
    def save_script(self):
        file = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if file:
            with open(file, "w", encoding="utf-8") as f:
                json.dump(self.actions, f, ensure_ascii=False, indent=2)
            self.log("腳本已儲存")

    def edit_action(self, event):
        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        action = self.actions[idx]
        
        if action["type"] == "wait":
            new_sec = simpledialog.askfloat("編輯等待時間", "輸入新秒數", initialvalue=action["data"], minvalue=0.1)
            if new_sec is not None:
                self.actions[idx]["data"] = new_sec
                self.refresh_listbox()
                
        elif action["type"] in ["click", "double_click"]:
            new_path = filedialog.askopenfilename(initialdir="targets", filetypes=[("Images", "*.png *.jpg *.jpeg")])
            if new_path:
                self.actions[idx]["data"] = new_path
                self.refresh_listbox()
                
        elif action["type"] == "scroll_down":
            new_amount = simpledialog.askinteger("編輯滾輪次數", "輸入滾輪向下次數", initialvalue=action["data"], minvalue=1)
            if new_amount is not None:
                self.actions[idx]["data"] = new_amount
                self.refresh_listbox()
                
        elif action["type"] == "conditional":
            # 彈出子動作編輯視窗
            sub_win = tk.Toplevel(self.root)
            sub_win.title(f"編輯條件子動作 - {os.path.basename(action['image'])}")
            sub_win.geometry("600x800")
            
            # 顯示/編輯 max_attempts
            attempts_frame = tk.Frame(sub_win)
            attempts_frame.pack(pady=5)
            tk.Label(attempts_frame, text="最大檢查次數 (-1=無限):").pack(side=tk.LEFT)
            attempts_entry = tk.Entry(attempts_frame)
            attempts_entry.insert(0, str(action.get('max_attempts', 1)))
            attempts_entry.pack(side=tk.LEFT, padx=5)
            tk.Button(attempts_frame, text="更新", command=lambda: self.update_max_attempts(idx, attempts_entry.get())).pack(side=tk.LEFT)
            
            tk.Label(sub_win, text="【找到圖片時】子動作", fg="green", font=("Consolas", 10, "bold")).pack(anchor="w", padx=10)
            found_list = tk.Listbox(sub_win, height=10, font=("Consolas", 10))
            found_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            for sub in action.get("found_actions", []):
                found_list.insert(tk.END, self.get_action_display_text(sub))
            tk.Button(sub_win, text="測試找到時子動作", command=lambda: self.test_sub_actions(action.get("found_actions", []))).pack(pady=5)
            
            tk.Label(sub_win, text="【沒找到圖片時】子動作", fg="red", font=("Consolas", 10, "bold")).pack(anchor="w", padx=10)
            not_found_list = tk.Listbox(sub_win, height=10, font=("Consolas", 10))
            not_found_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            for sub in action.get("not_found_actions", []):
                not_found_list.insert(tk.END, self.get_action_display_text(sub))
            tk.Button(sub_win, text="測試沒找到時子動作", command=lambda: self.test_sub_actions(action.get("not_found_actions", []))).pack(pady=5)
            
            tk.Button(sub_win, text="關閉", command=sub_win.destroy).pack(pady=10)

    def update_max_attempts(self, idx, new_value):
        try:
            value = int(new_value)
            if value == 0 or value < -1:
                raise ValueError
            self.actions[idx]["max_attempts"] = value
            self.refresh_listbox()
            self.log("最大檢查次數已更新")
        except:
            messagebox.showerror("錯誤", "請輸入有效數字（-1=無限，1以上=有限次）")

    def test_sub_actions(self, sub_actions):
        self.log("開始測試子動作序列...")
        for sub in sub_actions:
            if sub["type"] == "wait":
                self.log(f"模擬等待 {sub['data']} 秒")
            elif sub["type"] == "scroll_down":
                self.log(f"模擬滾輪向下 {sub['data']} 次")
            elif sub["type"] in ["click", "double_click"]:
                self.log(f"模擬 {sub['type']} 圖片: {os.path.basename(sub['data'])}")
            # 可以擴充其他類型
            time.sleep(0.5)  # 模擬延遲
        self.log("子動作測試完成")

    def on_drag_start(self, event):
        index = self.listbox.nearest(event.y)
        if index < 0: return
        self.drag_data["index"] = index
        self.drag_data["y"] = event.y

    def on_drag_motion(self, event):
        if self.drag_data["index"] is None: return
        new_index = self.listbox.nearest(event.y)
        if new_index < 0: new_index = len(self.actions) - 1
        
        current_index = self.drag_data["index"]
        if new_index != current_index:
            action = self.actions.pop(current_index)
            self.actions.insert(new_index, action)
            self.drag_data["index"] = new_index
            self.refresh_listbox()

    def on_drag_release(self, event):
        self.drag_data = {"index": None, "y": 0, "item": None}

    def capture_image_tool(self):
        self.log("請用滑鼠拖曳選擇範圍截圖...")
        self.root.withdraw()
        screenshot = ImageGrab.grab()
        self.capture_win = tk.Toplevel()
        self.capture_win.attributes('-fullscreen', True)
        self.capture_win.attributes('-alpha', 0.3)
        self.canvas = tk.Canvas(self.capture_win, cursor="cross", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.img_tk = ImageTk.PhotoImage(screenshot)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.img_tk)
        
        self.start_x = self.start_y = None
        self.rect = None
        
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
    
    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline="red", width=3)
    
    def on_drag(self, event):
        if self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)
    
    def on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)
        
        self.capture_win.destroy()
        self.root.deiconify()
        
        if x2 - x1 < 10 or y2 - y1 < 10:
            messagebox.showinfo("提示", "範圍太小，已取消")
            return
            
        cropped = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        
        # 彈出輸入框讓你取名字
        default_name = f"step_{len(os.listdir('targets')) + 1}"  # 預設名字
        new_name = simpledialog.askstring("圖片命名", "請輸入這張圖的描述名稱（不含副檔名）", initialvalue=default_name)
        
        if not new_name:
            new_name = f"target_{int(time.time())}"  # 如果取消，就用時間戳
        elif not new_name.endswith(".png"):
            new_name += ".png"
        
        save_path = os.path.join("targets", new_name)
        
        # 如果名字重複，加數字避免覆蓋
        counter = 1
        original_path = save_path
        while os.path.exists(save_path):
            name_without_ext = os.path.splitext(original_path)[0]
            ext = os.path.splitext(original_path)[1]
            save_path = f"{name_without_ext}_{counter}{ext}"
            counter += 1
        
        cropped.save(save_path)
        messagebox.showinfo("成功", f"已儲存為:\n{save_path}\n下次新增動作時會直接看到這個名字喔～")
        self.log("截圖並命名完成")

    def test_action(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("提示", "請先選取一個動作測試")
            return
        action = self.actions[sel[0]]
        
        if action["type"] == "wait":
            messagebox.showinfo("測試", f"這是等待 {action['data']} 秒")
            return
        
        try:
            image_to_find = action.get("image") if action["type"] == "conditional" else action.get("data")
            if not image_to_find: return

            loc = pyautogui.locateOnScreen(image_to_find, confidence=self.confidence, grayscale=True)
            if loc:
                pyautogui.moveTo(pyautogui.center(loc))
                self.log("測試成功：找到圖片")
            else:
                self.log("測試失敗：找不到圖片")
                messagebox.showwarning("失敗", "當前畫面上找不到該圖片")
        except Exception as e:
            messagebox.showerror("錯誤", str(e))

    def start_thread(self):
        if not self.actions:
            messagebox.showwarning("警告", "請先新增動作")
            return
        self.is_running = True
        threading.Thread(target=self.run_bot, daemon=True).start()
    
    def stop_bot(self):
        self.is_running = False
        self.log("已停止")
    
    def run_bot(self):
        self.log("開始執行...")
        self.progress["maximum"] = len(self.actions)
        
        while self.is_running:
            i = 0
            while i < len(self.actions):
                if not self.is_running: break
                
                # 更新進度條與選取狀態
                self.progress["value"] = i + 1
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i) # 確保滾動條跟著跑
                
                action = self.actions[i]
                
                if action["type"] == "wait":
                    self.log(f"等待 {action['data']} 秒...")
                    time.sleep(action["data"])
                    i += 1
                    
                elif action["type"] == "scroll_down":
                    self.log(f"滾輪向下 {action['data']} 次...")
                    pyautogui.scroll(-120 * action["data"])
                    time.sleep(0.5)
                    i += 1
                    
                elif action["type"] == "conditional":
                    self.log(f"條件檢查: {os.path.basename(action['image'])} (最多 {action['max_attempts']} 次)")
                    found = False
                    attempts = 0
                    max_att = action['max_attempts'] if action['max_attempts'] > 0 else float('inf')
                    
                    while attempts < max_att and not found and self.is_running:
                        attempts += 1
                        self.log(f"第 {attempts} 次檢查...")
                        try:
                            loc = pyautogui.locateOnScreen(action["image"], confidence=self.confidence, grayscale=True)
                            if loc:
                                found = True
                                self.log("找到圖片 → 執行「找到時」動作")
                                # 執行找到時的子動作
                                for sub_action in action.get("found_actions", []):
                                    if not self.is_running: break
                                    self.execute_single_action(sub_action)
                                break  # 找到就跳出循環
                        except:
                            pass
                        time.sleep(1)
                    
                    if not found:
                        self.log("沒找到圖片 → 執行「沒找到時」動作")
                        # 執行沒找到時的子動作
                        for sub_action in action.get("not_found_actions", []):
                            if not self.is_running: break
                            self.execute_single_action(sub_action)
                    
                    i += 1  # 條件動作結束，繼續下一主動作
                        
                else:
                    # 一般點擊
                    image_path = action["data"]
                    self.log(f"尋找 {os.path.basename(image_path)}...")
                    found = False
                    for _ in range(5): # 嘗試找5次
                        if not self.is_running: break
                        try:
                            loc = pyautogui.locateOnScreen(image_path, confidence=self.confidence, grayscale=True)
                            if loc:
                                center = pyautogui.center(loc)
                                if action["type"] == "double_click":
                                    pyautogui.doubleClick(center)
                                else:
                                    pyautogui.click(center)
                                found = True
                                break
                        except:
                            pass
                        time.sleep(1)
                    
                    if found:
                        i += 1
                    else:
                        # 找不到圖片的處理
                        self.log(f"找不到圖片: {os.path.basename(image_path)}")
                        # 如果需要找不到就停止，可取消下行註解
                        # break 
                        i += 1 # 暫時設為找不到也繼續下一步，避免卡死
                        
                time.sleep(0.5)
            
            if not self.loop_var.get():
                break
        
        self.is_running = False
        self.log("執行結束")
        self.progress["value"] = 0
        
    def execute_single_action(self, action):
        if action["type"] == "wait":
            time.sleep(action["data"])
        elif action["type"] == "scroll_down":
            pyautogui.scroll(-120 * action["data"])
            time.sleep(0.5)
        elif action["type"] in ["click", "double_click"]:
            image_path = action["data"]
            try:
                loc = pyautogui.locateOnScreen(image_path, confidence=self.confidence, grayscale=True)
                if loc:
                    center = pyautogui.center(loc)
                    if action["type"] == "double_click":
                        pyautogui.doubleClick(center)
                    else:
                        pyautogui.click(center)
            except:
                pass
        # 可以繼續擴充其他子動作類型

if __name__ == "__main__":
    root = tk.Tk()
    app = AutoBotUI(root)
    root.mainloop()