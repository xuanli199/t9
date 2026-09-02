#pragma once

#include "resource.h"

#include <string>

class T9KeySettingsDialog : public CDialogImpl<T9KeySettingsDialog> {
 public:
  enum { IDD = IDD_T9_KEY_SETTINGS };
  enum { kGroupCount = 10 };

 protected:
  BEGIN_MSG_MAP(T9KeySettingsDialog)
  MESSAGE_HANDLER(WM_INITDIALOG, OnInitDialog)
  MESSAGE_HANDLER(WM_CLOSE, OnClose)
  MESSAGE_HANDLER(WM_TIMER, OnTimer)
  COMMAND_HANDLER(IDC_T9_SCHEMA, CBN_SELCHANGE, OnSchemaSelChange)
  COMMAND_ID_HANDLER(IDC_T9_RESTORE, OnRestore)
  COMMAND_RANGE_HANDLER(IDC_T9_KEYBTN_BASE,
                        IDC_T9_KEYBTN_BASE + kGroupCount - 1, OnKeyBtn)
  COMMAND_ID_HANDLER(IDOK, OnOk)
  COMMAND_ID_HANDLER(IDCANCEL, OnCancelCmd)
  END_MSG_MAP()

  LRESULT OnInitDialog(UINT, WPARAM, LPARAM, BOOL&);
  LRESULT OnClose(UINT, WPARAM, LPARAM, BOOL&);
  LRESULT OnTimer(UINT, WPARAM, LPARAM, BOOL&);
  LRESULT OnSchemaSelChange(WORD, WORD, HWND, BOOL&);
  LRESULT OnRestore(WORD, WORD, HWND, BOOL&);
  LRESULT OnKeyBtn(WORD, WORD, HWND, BOOL&);
  LRESULT OnOk(WORD, WORD, HWND, BOOL&);
  LRESULT OnCancelCmd(WORD, WORD, HWND, BOOL&);

  static const wchar_t* kSchemaLabels[2];

  int CurrentSchema() const;
  void StartCapture(int group);
  void StopCapture();
  void PollCapturedKey();
  void LoadSchemaKeys(int schema);
  bool SaveSchemaKeys(int schema);
  void UpdateKeyButtons();
  void SetDefaults(int schema);

  CComboBox schema_combo_;
  HWND key_btn_[kGroupCount] = {};
  CString hint_text_;

  // keys_[schema][group] = rime 键名 (group 0..9 对应九键 1..9,0)
  std::string keys_[2][kGroupCount];
  bool manual_content_[2] = {false, false};
  bool dirty_[2] = {false, false};
  int capture_ = -1;  // 正在捕获按键的组号, -1 表示未捕获
  UINT_PTR capture_timer_ = 0;  // 捕获期间的轮询定时器
};
