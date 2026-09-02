#include "stdafx.h"
#include "T9KeySettingsDialog.h"
#include "WeaselDeployer.h"
#include <WeaselUtility.h>
#include <filesystem>
#include <fstream>
#include <regex>
#include <sstream>
#include <vector>

const wchar_t* T9KeySettingsDialog::kSchemaLabels[2] = {
    L"九键拼音 (t9)", L"九键位置对应 (t9_pos)"};

// 由此对话框生成的配置文件首行标记
static const char kMarker[] = "T9KeySettings-v1";
static const char kPatchKey[] = "key_binder/bindings/+";
static const char* kSchemaIds[2] = {"t9", "t9_pos"};

// 两个方案中各九键组的默认 accept 键 (小键盘)
// 下标 0..8 对应九键 1..9, 下标 9 对应九键 0
static const char* kDefaultKeys[2][10] = {
    {"KP_1", "KP_2", "KP_3", "KP_4", "KP_5", "KP_6", "KP_7", "KP_8", "KP_9",
     "KP_0"},
    {"KP_7", "KP_8", "KP_9", "KP_4", "KP_5", "KP_6", "KP_1", "KP_2", "KP_3",
     "KP_0"}};

// 九键 2..9 对应的字母组 (按钮第一行文字)
static const wchar_t* kGroupLetters[8] = {L"abc",  L"def", L"ghi", L"jkl",
                                          L"mno", L"pqrs", L"tuv", L"wxyz"};

static std::filesystem::path CustomYamlPath(int schema) {
  return WeaselUserDataPath() / (u8tow(kSchemaIds[schema]) + L".custom.yaml");
}

// 带返回值的消息框 (MSG_BY_IDS 宏无返回值)
static int ConfirmByIds(UINT id_info, UINT u_type) {
  CString info, cap;
  info.LoadStringW(id_info);
  cap.LoadStringW(IDS_STR_WEASEL);
  return MessageBoxExW(NULL, info, cap, u_type, GetThreadUILanguage());
}

// 组下标 -> 发送的数字 (0..8 对应 '1'..'9', 9 对应 '0')
static char GroupDigit(int group) {
  return (group < 9) ? char('1' + group) : '0';
}

// 方案 id 是否在此处结束 (后一个字符不是 id 组成部分)
static bool IsIdChar(char c) {
  return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
         (c >= '0' && c <= '9') || c == '_';
}

// 从文件内容中查找九键方案 id (返回 0=t9, 1=t9_pos, -1=未找到)
static int FindT9SchemaInText(const std::string& content,
                              const char* key_prefix) {
  size_t key_len = strlen(key_prefix);
  size_t pos = 0;
  while ((pos = content.find(key_prefix, pos)) != std::string::npos) {
    size_t v = pos + key_len;
    while (v < content.size() && (content[v] == ' ' || content[v] == '\t')) {
      ++v;
    }
    // 值可能被引号包裹: {schema: "t9_pos"}
    if (v < content.size() && (content[v] == '"' || content[v] == '\'')) {
      ++v;
    }
    if (content.compare(v, 6, "t9_pos") == 0 &&
        (v + 6 >= content.size() || !IsIdChar(content[v + 6]))) {
      return 1;
    }
    if (content.compare(v, 2, "t9") == 0 &&
        (v + 2 >= content.size() || !IsIdChar(content[v + 2]))) {
      return 0;
    }
    pos += key_len;
  }
  return -1;
}

// 探测用户当前在用的九键方案, 用于对话框初始选中:
// 1) user.yaml 的 previously_selected_schema (会话实际恢复的方案);
// 2) 否则取 default.custom.yaml / default.yaml 方案列表中第一个九键方案;
// 3) 都没有则默认第一项
static int DetectInitialSchema() {
  std::ifstream in(WeaselUserDataPath() / L"user.yaml", std::ios::binary);
  if (in) {
    std::string content((std::istreambuf_iterator<char>(in)),
                        std::istreambuf_iterator<char>());
    int found = FindT9SchemaInText(content, "previously_selected_schema:");
    if (found >= 0) {
      return found;
    }
  }
  const char* list_keys[2] = {"schema_list:", "schema:"};
  std::filesystem::path candidates[2] = {
      WeaselUserDataPath() / L"default.custom.yaml",
      WeaselSharedDataPath() / L"default.yaml"};
  for (const auto& path : candidates) {
    std::ifstream f(path, std::ios::binary);
    if (!f) {
      continue;
    }
    std::string content((std::istreambuf_iterator<char>(f)),
                        std::istreambuf_iterator<char>());
    for (const char* key : list_keys) {
      int found = FindT9SchemaInText(content, key);
      if (found >= 0) {
        return found;
      }
    }
  }
  return 0;
}

// rime 键名的友好显示 (小键盘键显示为"小键盘 x")
static std::wstring DisplayKeyName(const std::string& key) {
  if (key.empty()) {
    return L"-";
  }
  if (key.compare(0, 3, "KP_") == 0) {
    CString fmt, out;
    fmt.LoadStringW(IDS_STR_T9_KEYPAD_FMT);
    out.Format(fmt, u8tow(key.substr(3)).c_str());
    return (LPCTSTR)out;
  }
  return u8tow(key);
}

// 虚拟键码 -> rime 键名; 无法映射时返回空串
static std::string VkToRimeKey(DWORD vk) {
  // 带修饰键的组合不在此界面支持
  if ((GetAsyncKeyState(VK_CONTROL) & 0x8000) ||
      (GetAsyncKeyState(VK_MENU) & 0x8000) ||
      (GetAsyncKeyState(VK_LWIN) & 0x8000) ||
      (GetAsyncKeyState(VK_RWIN) & 0x8000)) {
    return "";
  }
  char buf[32] = {};
  if (vk >= 'A' && vk <= 'Z') {
    buf[0] = char('a' + (vk - 'A'));
    return buf;
  }
  if (vk >= '0' && vk <= '9') {
    buf[0] = char(vk);
    return buf;
  }
  if (vk >= VK_NUMPAD0 && vk <= VK_NUMPAD9) {
    _snprintf_s(buf, _TRUNCATE, "KP_%d", int(vk - VK_NUMPAD0));
    return buf;
  }
  if (vk >= VK_F1 && vk <= VK_F24) {
    _snprintf_s(buf, _TRUNCATE, "F%d", int(vk - VK_F1 + 1));
    return buf;
  }
  switch (vk) {
    case VK_SPACE: return "space";
    case VK_TAB: return "Tab";
    case VK_RETURN: return "Return";
    case VK_MULTIPLY: return "KP_Multiply";
    case VK_ADD: return "KP_Add";
    case VK_SUBTRACT: return "KP_Subtract";
    case VK_DECIMAL: return "KP_Decimal";
    case VK_DIVIDE: return "KP_Divide";
    case VK_INSERT: return "Insert";
    case VK_DELETE: return "Delete";
    case VK_HOME: return "Home";
    case VK_END: return "End";
    case VK_PRIOR: return "Page_Up";
    case VK_NEXT: return "Page_Down";
    case VK_UP: return "Up";
    case VK_DOWN: return "Down";
    case VK_LEFT: return "Left";
    case VK_RIGHT: return "Right";
    case VK_OEM_COMMA: return "comma";
    case VK_OEM_PERIOD: return "period";
    case VK_OEM_MINUS: return "minus";
    case VK_OEM_PLUS: return "equal";
    case VK_OEM_1: return "semicolon";
    case VK_OEM_7: return "apostrophe";
    case VK_OEM_2: return "slash";
    case VK_OEM_3: return "grave";
    case VK_OEM_4: return "bracketleft";
    case VK_OEM_6: return "bracketright";
    case VK_OEM_5: return "backslash";
  }
  return "";
}

// 按键捕获采用非阻塞设计: 点键位按钮后启动 WM_TIMER 轮询按键状态,
// 对话框消息循环始终正常运转, 捕获期间其余按钮均可正常点击
static const UINT_PTR kCaptureTimerId = 9001;

int T9KeySettingsDialog::CurrentSchema() const {
  int sel = schema_combo_.GetCurSel();
  return (sel < 0 || sel > 1) ? 0 : sel;
}

void T9KeySettingsDialog::SetDefaults(int schema) {
  for (int i = 0; i < kGroupCount; ++i) {
    keys_[schema][i] = kDefaultKeys[schema][i];
  }
}

// 去除首尾空白与包裹引号
static std::string Unquote(std::string s) {
  size_t start = s.find_first_not_of(" \t\r");
  if (start == std::string::npos) {
    return "";
  }
  size_t end = s.find_last_not_of(" \t\r");
  s = s.substr(start, end - start + 1);
  if (s.size() >= 2 && ((s.front() == '\'' && s.back() == '\'') ||
                        (s.front() == '"' && s.back() == '"'))) {
    s = s.substr(1, s.size() - 2);
  }
  return s;
}

void T9KeySettingsDialog::LoadSchemaKeys(int schema) {
  SetDefaults(schema);
  manual_content_[schema] = false;

  std::ifstream in(CustomYamlPath(schema), std::ios::binary);
  if (!in) {
    return;
  }
  std::string content((std::istreambuf_iterator<char>(in)),
                      std::istreambuf_iterator<char>());
  if (content.find(kMarker) == std::string::npos) {
    manual_content_[schema] = true;
  }

  static const std::regex binding_re(
      "^\\s*-\\s*\\{\\s*accept:\\s*([^,}]+)\\s*,\\s*send:\\s*'?([0-9])'?"
      "\\s*,\\s*when:\\s*(?:always|composing)\\s*\\}\\s*$");
  std::istringstream stream(content);
  std::string line;
  while (std::getline(stream, line)) {
    if (!line.empty() && line.back() == '\r') {
      line.pop_back();
    }
    size_t first = line.find_first_not_of(" \t");
    if (first == std::string::npos || line[first] == '#' ||
        line.compare(first, 6, "patch:") == 0 ||
        line.find(kPatchKey) != std::string::npos) {
      continue;
    }
    std::smatch match;
    if (std::regex_match(line, match, binding_re)) {
      std::string accept = Unquote(match[1].str());
      char digit = match[2].str()[0];
      int group = (digit == '0') ? 9 : (digit - '1');
      if (!accept.empty() && group >= 0 && group < kGroupCount) {
        keys_[schema][group] = accept;
      } else {
        manual_content_[schema] = true;
      }
    } else {
      manual_content_[schema] = true;
    }
  }
}

bool T9KeySettingsDialog::SaveSchemaKeys(int schema) {
  // 收集与默认不同的绑定; 全部为默认则直接删除配置文件
  std::vector<std::pair<std::string, char>> entries;
  for (int i = 0; i < kGroupCount; ++i) {
    if (keys_[schema][i] != kDefaultKeys[schema][i]) {
      entries.push_back({keys_[schema][i], GroupDigit(i)});
    }
  }
  if (entries.empty()) {
    std::error_code ec;
    std::filesystem::remove(CustomYamlPath(schema), ec);
    manual_content_[schema] = false;
    dirty_[schema] = false;
    return true;
  }

  if (manual_content_[schema]) {
    if (ConfirmByIds(IDS_STR_T9_CONFIRM_OVERWRITE,
                     MB_YESNO | MB_ICONQUESTION) != IDYES) {
      return false;
    }
  }

  std::string content;
  content += "# ";
  content += kMarker;
  content += " generated by WeaselDeployer (do not edit the marker line)\r\n";
  content += "patch:\r\n";
  content += std::string("  ") + kPatchKey + ":\r\n";
  for (const auto& entry : entries) {
    // 纯数字值加引号, 避免被 YAML 解析为整数
    std::string send(1, '\'');
    send += entry.second;
    send += '\'';
    // send 为数字, when 用 always (与方案内小键盘默认绑定一致;
    // 英文模式下引擎在 ascii_composer 处即直通, 不会误触)
    content += "    - {accept: " + entry.first + ", send: " + send +
               ", when: always}\r\n";
  }

  std::ofstream out(CustomYamlPath(schema), std::ios::binary | std::ios::trunc);
  if (!out) {
    return false;
  }
  out << content;
  out.close();
  manual_content_[schema] = false;
  dirty_[schema] = false;
  return true;
}

// 按钮第一行: 九键组的字母/功能标签
static std::wstring GroupLabel(int group) {
  wchar_t buf[64] = {};
  if (group == 0) {
    CString label;
    label.LoadStringW(IDS_STR_T9_GROUP_PUNCT);
    _snwprintf_s(buf, _TRUNCATE, L"1 %s", (LPCTSTR)label);
  } else if (group == 9) {
    CString label;
    label.LoadStringW(IDS_STR_T9_GROUP_SPACE);
    _snwprintf_s(buf, _TRUNCATE, L"0 %s", (LPCTSTR)label);
  } else {
    _snwprintf_s(buf, _TRUNCATE, L"%d %s", group + 1,
                 kGroupLetters[group - 1]);
  }
  return buf;
}

void T9KeySettingsDialog::UpdateKeyButtons() {
  int schema = CurrentSchema();
  for (int i = 0; i < kGroupCount; ++i) {
    if (!key_btn_[i]) {
      continue;
    }
    std::wstring text = GroupLabel(i);
    text += L"\r\n";
    text += DisplayKeyName(keys_[schema][i]);
    ::SetWindowTextW(key_btn_[i], text.c_str());
  }
}

LRESULT T9KeySettingsDialog::OnInitDialog(UINT, WPARAM, LPARAM, BOOL&) {
  schema_combo_.Attach(GetDlgItem(IDC_T9_SCHEMA));
  for (int i = 0; i < kGroupCount; ++i) {
    key_btn_[i] = GetDlgItem(IDC_T9_KEYBTN_BASE + i);
  }
  ::GetDlgItemTextW(m_hWnd, IDC_T9_HINT, hint_text_.GetBuffer(512), 512);
  hint_text_.ReleaseBuffer();

  for (int i = 0; i < 2; ++i) {
    schema_combo_.AddString(kSchemaLabels[i]);
  }
  // 默认选中用户当前在用的方案
  schema_combo_.SetCurSel(DetectInitialSchema());

  LoadSchemaKeys(0);
  LoadSchemaKeys(1);
  UpdateKeyButtons();

  CenterWindow();
  BringWindowToTop();
  return TRUE;
}

LRESULT T9KeySettingsDialog::OnClose(UINT, WPARAM, LPARAM, BOOL&) {
  StopCapture();
  EndDialog(IDCANCEL);
  return 0;
}

LRESULT T9KeySettingsDialog::OnTimer(UINT, WPARAM wParam, LPARAM, BOOL&) {
  if (wParam == kCaptureTimerId) {
    PollCapturedKey();
  }
  return 0;
}

LRESULT T9KeySettingsDialog::OnSchemaSelChange(WORD, WORD, HWND, BOOL&) {
  StopCapture();
  UpdateKeyButtons();
  return 0;
}

LRESULT T9KeySettingsDialog::OnKeyBtn(WORD, WORD wID, HWND, BOOL&) {
  int group = wID - IDC_T9_KEYBTN_BASE;
  if (group < 0 || group >= kGroupCount) {
    return 0;
  }
  StartCapture(group);
  return 0;
}

void T9KeySettingsDialog::StartCapture(int group) {
  if (capture_timer_) {
    ::KillTimer(m_hWnd, capture_timer_);
    capture_timer_ = 0;
  }
  capture_ = group;
  // 基准: 清除各键"上次查询后曾按下"状态, 避免捕获到旧按键
  for (DWORD vk = 0; vk < 256; ++vk) {
    GetAsyncKeyState(vk);
  }
  CString capturing;
  capturing.LoadStringW(IDS_STR_T9_CAPTURING);
  ::SetDlgItemTextW(m_hWnd, IDC_T9_HINT, capturing);
  capture_timer_ = ::SetTimer(m_hWnd, kCaptureTimerId, 15, NULL);
}

void T9KeySettingsDialog::StopCapture() {
  if (capture_timer_) {
    ::KillTimer(m_hWnd, capture_timer_);
    capture_timer_ = 0;
  }
  if (capture_ >= 0) {
    capture_ = -1;
    ::SetDlgItemTextW(m_hWnd, IDC_T9_HINT, hint_text_);
  }
}

// 定时器回调: 每次扫描一遍按键状态, 捕获到结果即结束
void T9KeySettingsDialog::PollCapturedKey() {
  int group = capture_;
  if (group < 0) {
    return;
  }
  int schema = CurrentSchema();
  for (DWORD vk = VK_BACK; vk <= VK_PACKET; ++vk) {
    if (vk == VK_LBUTTON || vk == VK_RBUTTON || vk == VK_MBUTTON ||
        vk == VK_XBUTTON1 || vk == VK_XBUTTON2) {
      continue;  // 鼠标键不参与捕获
    }
    if (!(GetAsyncKeyState(vk) & 1)) {
      continue;
    }
    if (vk == VK_ESCAPE) {
      StopCapture();  // 取消捕获
      return;
    }
    if (vk == VK_BACK) {
      keys_[schema][group] = kDefaultKeys[schema][group];  // 恢复该组默认
      dirty_[schema] = true;
      UpdateKeyButtons();
      StopCapture();
      return;
    }
    if (vk == VK_SHIFT || vk == VK_CONTROL || vk == VK_MENU ||
        vk == VK_CAPITAL) {
      continue;  // 单独的修饰键: 继续等待
    }
    std::string key = VkToRimeKey(vk);
    if (key.empty()) {
      continue;
    }
    bool used = false;
    for (int i = 0; i < kGroupCount; ++i) {
      if (i != group && keys_[schema][i] == key) {
        CString fmt, msg, cap;
        fmt.LoadStringW(IDS_STR_T9_KEY_USED_FMT);
        msg.Format(fmt, GroupLabel(i).c_str());
        cap.LoadStringW(IDS_STR_WEASEL);
        MessageBoxExW(m_hWnd, msg, cap, MB_OK | MB_ICONWARNING,
                      GetThreadUILanguage());
        used = true;
        break;
      }
    }
    if (!used) {
      keys_[schema][group] = key;
      dirty_[schema] = true;
      UpdateKeyButtons();
      StopCapture();
      return;
    }
    // 按键已被占用: 提示后继续等待下一个按键
    return;
  }
}

LRESULT T9KeySettingsDialog::OnRestore(WORD, WORD, HWND, BOOL&) {
  StopCapture();
  int schema = CurrentSchema();
  if (ConfirmByIds(IDS_STR_T9_CONFIRM_RESTORE,
                   MB_YESNO | MB_ICONQUESTION) != IDYES) {
    return 0;
  }
  std::error_code ec;
  std::filesystem::remove(CustomYamlPath(schema), ec);
  SetDefaults(schema);
  manual_content_[schema] = false;
  dirty_[schema] = false;
  UpdateKeyButtons();
  return 0;
}

LRESULT T9KeySettingsDialog::OnOk(WORD, WORD, HWND, BOOL&) {
  StopCapture();  // 捕获中被点击: 放弃未完成的捕获, 照常保存
  for (int schema = 0; schema < 2; ++schema) {
    if (dirty_[schema] && !SaveSchemaKeys(schema)) {
      // 用户在覆盖确认中选择了"否", 停留在对话框
      schema_combo_.SetCurSel(schema);
      UpdateKeyButtons();
      return 0;
    }
  }
  EndDialog(IDOK);
  return 0;
}

LRESULT T9KeySettingsDialog::OnCancelCmd(WORD, WORD, HWND, BOOL&) {
  StopCapture();
  EndDialog(IDCANCEL);
  return 0;
}
