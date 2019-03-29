# mitsubishi-cnc-m700
三菱電機CNC M700シリーズとEZSocketを使って通信するPythonのサンプルです。

Windows環境で、COMオブジェクトを利用することで動作します。

自身の環境で実装する際のヒントとしてお使い下さい。

# 実装機能
- DデバイスとMデバイスへの値の読み込みと書き込み
- NCの状態やツール番号や回転数などの情報取得
- NC内のディレクト検索とファイルの操作（read・write・delete）

# 参考情報

## Windows環境で、以下の三菱CNC通信用ソフトウェア開発キットが必要です
http://www.mitsubishielectric.co.jp/fa/download/software/detailsearch.do?mode=software&kisyu=/cnc&shiryoid=0000000030&lang=1&select=0&softid=1&infostatus=3_11_2&viewradio=0&viewstatus=&viewpos=

### 三菱CNC用通信ソフトウェア　FCSB1224W000 リファレンスマニュアル
http://www.mitsubishielectric.co.jp/fa/document/others/cnc/ib-1501208/IB-1501208.pdf

### COMへVARIANT型の引数をPythonから渡す方法
http://docs.activestate.com/activepython/3.4/pywin32/html/com/win32com/HTML/variant.html
https://mail.python.org/pipermail/python-win32/2012-October/012575.html

### pythoncom.VT_VARIANTの型一覧
http://nullege.com/codes/search/pythoncom.VT_VARIANT


# 使い方

```
# Open connection
m700 = M700.get_connection('192.168.1.10:683')

# NC内情報取得
m700.get_drive_infomation()
m700.get_run_status()
m700.get_alerm()

# Dデバイスへの操作
m700.write_dev('M900', 1)
m700.read_dev('M900') # -> 1

# Mデバイスへの操作
m700.write_dev('D200', 10)
m700.read_dev('D200') # -> 10

# 加工プログラムのファイルの操作（read・write・delete）
drivenm = m700.get_drive_infomation()
m700.write_file(drivenm + '¥PRG¥USER¥__TEST__.txt', b'TEST_WRITE')
m700.read_file(drivenm + '¥PRG¥USER¥__TEST__.txt')
m700.delete_file(drivenm + '¥PRG¥USER¥__TEST__.txt')

# Close connection
m700.close()
```
