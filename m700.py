# coding: utf-8
'''
三菱電機CNC M700シリーズとEZSocketを使って通信する。
通信対象はマシニングセンタ系三菱CNC M700/M700V/M70/M70V。
'''
from enum import Enum
import threading

import pythoncom
import win32com.client
from win32com.client import VARIANT
    

class M700():

    #同一スレッド内で同一ホストの接続は同じインスタンスを使う
    #同一スレッドなのは、COMオブジェクトを別スレッドで共有するのが複雑なため
    __connections = {}
    @classmethod
    def get_connection(cls, host):
        key = str(threading.current_thread().ident) + "_" + host
        if key not in cls.__connections:
            cls.__connections[key] = M700(host)
        return cls.__connections[key]
    
    #1-255の一意の値管理
    __uno_list = [False]*255
    @classmethod
    def alloc_unitno(cls):
        '''EZSocketで未使用のユニット番号を返す。

        Returns:
            int: ユニット番号
        '''
        for i,v in enumerate(cls.__uno_list):
            if v == False:
                cls.__uno_list[i] = True
                return i+1
        raise Exception("ユニット番号が255を超えました。同時接続数が多すぎます")
    
    @classmethod
    def release_unitno(cls, uno):
        cls.__uno_list[uno-1] = False
    
    # --- クラス内利用列挙体 ---
    
    class RunStatus(Enum):
        '''運転状態（valueはM700の返される値に対応している）'''
        NOT_AUTO_RUN = 0
        AUTO_RUN = 1

    class Position(Enum):
        '''X,Y,Z座標指定（valueはM700の返される値に対応している）'''
        X = 1
        Y = 2
        Z = 3

    class ProgramType(Enum):
        '''メインorサブプログラム（valueはM700の返される値に対応している）'''
        MAIN = 0
        SUB = 1

    class NCProgramFileOpenMode(Enum):
        '''NC内のプログラムファイルを開く際にしているするモード'''
        READ = 1
        WRITE = 2
        OVER_WRITE = 3

    __ip = None
    __port = None
    __isopen = False
    __ezcom = None
    __lock = threading.RLock()

    def __init__(self, host):
        '''
        Args:
            host: IPアドレス:ポート番号
        '''
        pythoncom.CoInitialize() # 複数スレッドで実行する際は、COMオブジェクトの初期化が必要
        self.__ip, self.__port = host.split(':')

    def __str__(self):
        return self.__ip + ":" + self.__port + " " + ("Open" if self.__isopen else "Close")

    def __open(self):
        '''引数として与えられたIPとユニット番号に対してコネクションを開く。
        すでにオープン後に再度呼び出された場合は何もしない。'''
        if not self.__isopen:
            self.__ezcom = win32com.client.Dispatch('EZNcAut.DispEZNcCommunication')
            errcd = self.__ezcom.SetTCPIPProtocol(self.__ip, int(self.__port))
            self.__unitno = M700.alloc_unitno()
            self.__raise_error(errcd)
            # 引数: マシンタイプ番号(固定), ユニット番号, タイムアウト100ミリ秒, COMホスト名
            #      マシンタイプ6=EZNC_SYS_MELDAS700M（マシニングセンタ系三菱CNC M700/M700V/M70/M70V）
            #      ユニット番号は、1~255内で一意ものを指定する必要がある。
            errcd = self.__ezcom.Open2(6, self.__unitno, 30, 'EZNC_LOCALHOST')
            self.__raise_error(errcd)
            self.__isopen = True

    def close(self):
        '''コネクションを閉じる。
        内部でエラーが起こっても例外は呼び出し元に返さない
        '''
        try:
            M700.release_unitno(self.__unitno) #ユニット番号の開放
            self.__isopen = False
            self.__ezcom.Close()
        except:
            pass
        try:
            self.__ezcom.Release()
        except:
            pass

    def is_open(self):
        '''__open()処理後、接続が開いているか確認する。
        
        Return:
            bool: 接続が開いているならTrue
        '''
        with self.__lock:
            try:
                self.__open()
            except:
                pass
            return self.__isopen

    # --- NC情報取得関連 ---

    def get_drive_infomation(self):
        '''利用可能なドライブ名を返す。
        注意：ドライブ名は本来 "ドライブ名:CRLFドライブ名:CRLF...ドライブ名:CRLF¥0"で取得するので、
        複数のドライブが存在する場合は、splitする必要がある。
        
        Return:
            str: ドライブ情報
        '''
        with self.__lock:
            self.__open()
            errcd, drive_info = self.__ezcom.File_GetDriveInformation()
            self.__raise_error(errcd)
            return drive_info[0:4]

    def get_version(self):
        '''NCのバージョンを返す
        
        Return:
            str: バージョン情報
        '''
        with self.__lock:
            self.__open()
            errcd, version = self.__ezcom.System_GetVersion(1, 0)
            self.__raise_error(errcd)
            return version

    def get_current_position(self, axisno):
        '''現在座標位置取得。

        Args:
            axisno (M700.Position.*): X or Y or Zを引数に渡す。
        
        Return:
            float: 現在座標位置
        '''
        with self.__lock:
            if not isinstance(axisno, M700.Position):
                raise Exception('列挙体[M700.Position.*]を指定してください。')
            # in_1：取得したい軸。1=x, 2=y, 3=z
            # pos：現在位置。
            self.__open()
            errcd, pos = self.__ezcom.Position_GetCurrentPosition(axisno.value)
            self.__raise_error(errcd)
            return pos

    def get_run_status(self):
        '''運転状態取得。

        Return:
            M700.RunStatus: 列挙体[M700.RunStatus]を返す。
        '''
        with self.__lock:
            # in_1：運転の種類。1=自動運転中であるか?
            # status：0=自動運転中でない。1=自動運転中である。
            self.__open()
            errcd, status = self.__ezcom.Status_GetRunStatus(1)
            self.__raise_error(errcd)
            if M700.RunStatus.AUTO_RUN.value == status:
                return M700.RunStatus.AUTO_RUN
            else:
                return M700.RunStatus.NOT_AUTO_RUN

    def get_rpm(self):
        '''回転数（0~[rpm]）取得。
        
        Return:
            int: 回転数
        '''
        with self.__lock:
            # in_1：指定した主軸のパラメータ番号を指定。2=主軸(SR、SF)回転速度。0~[rpm]
            # in_2：主軸番号を指定。
            # data：主軸の状態を返す。
            # info：主軸情報をUNICODE文字列として取得。
            self.__open()
            errcd, data, info = self.__ezcom.Monitor_GetSpindleMonitor(2, 1)
            self.__raise_error(errcd)
            return data

    def get_load(self):
        '''負荷（0~[%]）取得。
        
        Return:
            int: 負荷
        '''
        with self.__lock:
            # in_1：指定した主軸のパラメータ番号を指定。3=ロード。主軸モータの負荷。0~[%]
            # in_2：主軸番号を指定。
            # data：主軸の状態を返す。
            # info：主軸情報をUNICODE文字列として取得。
            self.__open()
            errcd, data, info = self.__ezcom.Monitor_GetSpindleMonitor(3, 1)
            self.__raise_error(errcd)
            return data

    def get_mgn_size(self):
        '''マガジンサイズ取得。
        
        Return:
            int: マガジンサイズ
        '''
        with self.__lock:
            # size：マガジンポットの総組数。値:0~360(最大)。
            self.__open()
            errcd, size = self.__ezcom.ATC_GetMGNSize()
            self.__raise_error(errcd)
            return size

    def get_mgn_ready(self):
        '''装着済みの工具番号取得。

        Return:
            int: 工具番号
        '''
        with self.__lock:
            # in_1：マガジン番号を指定。値:1~2(M700/M800シリーズでは、値を設定しても無効)
            # in_2：待機状態を指定。0=装着の工具番号、1=待機1の工具番号。2,3,4=1と同じ。
            # toolno：工具の番号を返す。値は、1~99999999(最大)
            self.__open()
            errcd, toolno = self.__ezcom.ATC_GetMGNReady2(1, 0)
            self.__raise_error(errcd)
            return toolno

    def get_toolset_size(self):
        '''ツールセットのサイズ取得
        ツールセットとは補正値NOのこと
        
        Return:
            int: ツールセットサイズ
        '''
        with self.__lock:
            # plSize：200=200[組]
            self.__open()
            errcd, size = self.__ezcom.Tool_GetToolSetSize()
            self.__raise_error(errcd)
            return size

    def get_tool_offset_h(self, toolset_no):
        '''工具組番号の長オフセット値

        Return:
            int: 長
        '''
        with self.__lock:
            # lType：工具オフセットのタイプ 4=マシニングセンタ系タイプⅡ
            # lKind：オフセット量の種類 0=長, 1=長摩耗, 2=径, 3=径摩耗
            # lToolSetNo：工具組番号
            # pdOffset As DOUBLE* (O)オフセット量
            # plNo As LONG* (O)仮想刃先点番号
            self.__open()
            errcd, h, plno = self.__ezcom.Tool_GetOffset2(4, 0, toolset_no)
            self.__raise_error(errcd)
            return h
    
    def get_tool_offset_d(self, toolset_no):
        '''工具組番号の長オフセット径
        
        Return:
            int: 径
        '''
        with self.__lock:
            self.__open()
            errcd, d, plno = self.__ezcom.Tool_GetOffset2(4, 2, toolset_no)
            self.__raise_error(errcd)
            return d

    def set_tool_offset_h(self, toolset_no, h):
        '''工具組番号オフセット長補正値をセットする'''
        with self.__lock:
            # lType：工具オフセットのタイプ 4=マシニングセンタ系タイプⅡ
            # lKind：オフセット量の種類 0=長, 1=長摩耗, 2=径, 3=径摩耗
            # lToolSetNo：工具組番号
            # pdOffset As DOUBLE* オフセット量
            # plNo As LONG* 仮想刃先点番号
            self.__open()
            errcd = self.__ezcom.Tool_SetOffset(4, 0, toolset_no, h, 0)
            self.__raise_error(errcd)
            errcd = self.__ezcom.Tool_SetOffset(4, 2, toolset_no, d, 0)
            self.__raise_error(errcd)

    def set_tool_offset_d(self, toolset_no, d):
        '''工具組番号オフセット径補正値をセットする'''
        with self.__lock:
            self.__open()
            errcd = self.__ezcom.Tool_SetOffset(4, 2, toolset_no, d, 0)
            self.__raise_error(errcd)

    def get_program_number(self, progtype):
        '''サーチ完了、又は自動運転中のプログラムの番号を取得。

        Args:
            progtype (M700.ProgramType.*): MAIN or SUBを引数に渡す。

        Return:
            str: プログラム番号
        '''
        with self.__lock:
            if not isinstance(progtype, M700.ProgramType):
                raise Exception('列挙体[M700.ProgramType.*]を指定してください。')
            
            # in_1：0=メインプログラム, 1=サブプログラム
            self.__open()
            errcd, msg = self.__ezcom.Program_GetProgramNumber2(progtype.value)
            self.__raise_error(errcd)
            return msg
        
    def get_alerm(self):
        '''アラートを取得。

        Return:
            str: エラーメッセージ
        '''
        with self.__lock:
            # in_1：取得するメッセージ行数。1~10(最大)
            # in_2：取得するアラーム種類。
            # msg：エラーメッセージ
            self.__open()
            errcd, msg = self.__ezcom.System_GetAlarm2(3, 0)
            self.__raise_error(errcd)
            return msg

    # --- NCプログラムファイル操作関連 ---

    def read_file(self, path):
        '''ファイルを読み出しする。

        Args:
            path (str): 絶対パス exp) M01:¥PRG¥USER¥100
        Return:
            bytes: 読み出したバイトデータを返す。
        '''
        with self.__lock:
            self.__open()
            try:
                errcd = self.__ezcom.File_OpenFile3(path, M700.NCProgramFileOpenMode.READ.value)
                self.__raise_error(errcd)
                result = b''
                while True:
                    errcd, data = self.__ezcom.File_ReadFile2(256) #一回で読み出すデータサイズをバイト数
                    self.__raise_error(errcd)
                    result += data #読み出したバイトデータの配列をVARIANT
                    if len(data) < 256:
                        break
                return result
            finally:
                try:
                    self.__ezcom.File_CloseFile2()
                except:
                    pass

    def write_file(self, path, data):
        '''ファイルに書き込みする。

        Args:
            path (str): 絶対パス exp) M01:¥PRG¥USER¥100
            data (bytes): 書き込むデータをバイトデータで渡す
        '''
        with self.__lock:
            self.__open()
            try:
                errcd = self.__ezcom.File_OpenFile3(path, M700.NCProgramFileOpenMode.OVER_WRITE.value)
                self.__raise_error(errcd)
                errcd = self.__ezcom.File_WriteFile(memoryview(data)) #書き込むデータをバイトデータの配列
                self.__raise_error(errcd)
            finally:
                try:
                    self.__ezcom.File_CloseFile2()
                except:
                    pass

    def delete_file(self, path):
        '''パス名を指定してファイルを削除する。

        Args:
            path (str): 絶対パス exp) M01:¥PRG¥USER¥100
        '''
        with self.__lock:
            self.__open()
            errcd = self.__ezcom.File_Delete2(path)
            self.__raise_error(errcd)

    # --- NCディレクトリ操作関連 --

    def find_dir(self, path):
        '''パス名を指定してファイルを検索する。

        Args:
            path (str): ディレクトリパス exp) M01:¥PRG¥USER¥
        Return:
            list: 検索結果のリスト。中身は辞書データで1件ごとのデータを管理。
                  exp) [{ 'type': 'file', 'name': '100', 'size': '19', 'comment': 'BY IKEHARA' }, ...]
        '''
        with self.__lock:
            result = []
            
            try:
                self.__open()
                
                #M01 → Mユニット番号16進数
                path = path.replace("M01", "M{:02X}".format(self.__unitno))

                # 指定パス内のディレクトリ情報を取得 (-1で'ディレクトリ名\tサイズ'の文字列を取得)
                errcd, info = self.__ezcom.File_FindDir2(path, -1)
                self.__raise_error(errcd)
                while True:
                    # ディレクトリ情報有り
                    if errcd > 1:
                        dir_info = info.split('\t')
                        data = {
                            'type': 'folder',
                            'name': dir_info[0],
                            'size': '{:,}'.format(int(dir_info[1])),
                            'comment': None
                        }
                        result.append(data)
                    else:
                        break
                    errcd, info = self.__ezcom.File_FindNextDir2()
                    self.__raise_error(errcd)
                
                # 一旦リセット
                errcd = self.__ezcom.File_ResetDir()
                self.__raise_error(errcd)

                # 指定パス内のファイル情報を取得 (5で'ファイル名\tサイズ\tコメント'の文字列を取得)
                errcd, info = self.__ezcom.File_FindDir2(path, 5)
                self.__raise_error(errcd)
                while True:
                    # ファイル情報有り
                    if errcd > 1:
                        dir_info = info.split('\t')
                        data = {
                            'type': 'file',
                            'name': dir_info[0],
                            'size': '{:,}'.format(int(dir_info[1])),
                            'comment': dir_info[2]
                        }
                        result.append(data)
                    else:
                        break
                    errcd, info = self.__ezcom.File_FindNextDir2()
                    self.__raise_error(errcd)
            finally:
                try:
                    errcd = self.__ezcom.File_ResetDir()
                    self.__raise_error(errcd)
                except:
                    pass

            return result
                    
    # --- NCデバイス操作関連 ---

    def __setting_dev(self, dev, data=0):
        '''デバイスの設定を行う。

        Args:
            dev (str): デバイス指定。exp) M810, D10
            data (int): 値。ビットを立てる場合は1、下げる場合は0。 
                        read_devの場合は、ダミーとして適当な文字を入れる。
        '''
        data_type = 0 # 1 or 4 or 8 exp) M=1(ビット型 1bit), D=4(ワード型 16bit)
        if dev[0] == 'M':
            data_type = 1
        elif dev[0] == 'D':
            data_type = 4
        else:
            Exception('Mデバイス、又はDデバイスを設定して下さい。')
        
        # in_1：デバイス文字列（設定するデバイス文字列の配列をVARIANTとして指定）
        # in_2：データ種別
        # in_3：デバイス値配列
        vDevice = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, [dev])
        vDataType = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, [data_type])
        vValue = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_I4, [data]) # 書き込むデータは現在数値のみ
        errcd = self.__ezcom.Device_SetDevice(vDevice, vDataType, vValue)
        self.__raise_error(errcd)

    def __delall_dev(self):
        '''デバイス設定を全て削除。'''
        errcd = self.__ezcom.Device_DeleteAll()
        self.__raise_error(errcd)

    def read_dev(self, dev):
        '''デバイス読み出し。__setting_devで設定したデバイスの値を読み込む。
        
        Args:
            dev (str): デバイス番号 exp) M900
        Return:
            int: 読み出したデータの値を返す。
        '''
        with self.__lock:
            self.__open()
            self.__setting_dev(dev)
            errcd, value = self.__ezcom.Device_Read() # value：デバイス値配列が返ってくる。
            self.__raise_error(errcd)
            self.__delall_dev()
            return value[0]

    def write_dev(self, dev, data):
        '''デバイス書き込み。__setting_devで設定したデバイスに値を書き込む。
        
        Args:
            dev (str): デバイス番号 exp) M900
            data (int): 書き込む値
        '''
        with self.__lock:
            self.__open()
            self.__setting_dev(dev, data)
            errcd = self.__ezcom.Device_Write()
            self.__delall_dev()
            self.__raise_error(errcd)

    # --- エラー出力関連 ---

    def __raise_error(self, errcd):
        '''エラーコードから、エラーの内容をExceptionとして返す。

        エラーがない場合（エラーコードが0）は何もしない。
        エラーの内容は、辞書で {'16進数エラーコード': 'error detail message'} の形で登録。

        Raises:
            Exception: エラーメッセージ
        '''
        __errmap = {
            "0x80a00101" : "通信回線がオープンされていません",
            "0x80a00104" : "2重オープンエラー",
            "0x80a00105" : "引数のデータタイプが不正",
            "0x80a00106" : "引数のデータ範囲が不正",
            "0x80a00107" : "サポートしていない",
            "0x80a00109" : "通信回線がオープンできません",
            "0x80a0010a" : "引数がnullポインタです。",
            "0x80a0010b" : "引数のデータ不正",
            "0x80a0010c" : "COMMポートハンドルエラー",
            "0x80b00101" : "メモリの確保ができない",
            "0x80b00102" : "EZSocketPcのエラーが取得できない",
            "0x80b00201" : "モード指定不正",
            "0x80b00202" : "未ファイルオープン",
            "0x80b00203" : "ファイルが既に存在する",
            "0x80b00204" : "既にファイルオープンしている",
            "0x80b00205" : "テンポラリファイルを作成できない",
            "0x80b00206" : "書き込みモード指定でファイルオープンしていない",
            "0x80b00207" : "書き込みデータサイズ不正",
            "0x80b00208" : "書き込みできない状態",
            "0x80b00209" : "読み出しモード指定でファイルオープンしていない",
            "0x80b0020a" : "読み出しできない状態",
            "0x80b0020b" : "テンポラリファイルを作成できない",
            "0x80b0020c" : "ファイルが存在しない（readモード）",
            "0x80b0020d" : "ファイルがオープンできない",
            "0x80b0020e" : "ファイルのパスが不正",
            "0x80b0020f" : "読み出しファイルが不正",
            "0x80b00210" : "書き込みファイルが不正",
            "0x80b00301" : "オートメーション呼び出しでローカル接続時のホスト名が不正",
            "0x80b00302" : "TCP/IP通信が設定されていない",
            "0x80b00303" : "既に通信中なので設定できない",
            "0x80b00304" : "下位モジュールがない",
            "0x80b00305" : "EZSocketPcオブジェクトが生成できない",
            "0x80b00401" : "データが存在しない",
            "0x80b00402" : "データ重複",
            "0x80b00501" : "パラメータ情報ファイルがない",
            "0x80020190" : "NCカード番号不正",
            "0x80020102" : "デバイスがオープンされていない",
            "0x80020132" : "コマンド不正",
            "0x80020133" : "通信パラメータデータ範囲不正",
            "0x80030143" : "ファイルシステムに異常がある",
            "0x80030191" : "ディレクトリが存在しない",
            "0x8003019b" : "ドライブが存在しない",
            "0x800301a2" : "ディレクトリが存在しない",
            "0x800301a8" : "ドライブが存在しない",
            "0x80050d90" : "系統、軸指定が不正",
            "0x80050d02" : "アラーム種類が不正",
            "0x80050d03" : "NCとPC間の通信データにエラーがある",
            "0x80041194" : "寿命管理データの種類指定不正",
            "0x80041195" : "設定データ範囲オーバ",
            "0x80041196" : "設定工具番号不一致",
            "0x80041197" : "指定工具番号が仕様外",
            "0x80040190" : "系統、軸指定が不正",
            "0x80040191" : "大区分番号不正",
            "0x80040192" : "小区分番号不正",
            "0x80040196" : "アプリケーションが用意したバッファに入りきらない",
            "0x80040197" : "データタイプ不正",
            "0x8004019d" : "データが読み出せない状態にある",
            "0x8004019f" : "書き込み専用データ",
            "0x800401a0" : "軸指定不正",
            "0x800401a1" : "データ番号不正",
            "0x800401a3" : "読み出しデータなし",
            "0x8004019a" : "読み出しデータ範囲不正",
            "0x80040290" : "系統、軸指定が不正",
            "0x80040291" : "大区分番号不正",
            "0x80040292" : "小区分番号不正",
            "0x80040296" : "アプリケーションが用意したバッファに入りきらない",
            "0x80040297" : "データタイプ不正",
            "0x8004029b" : "読み出し専用データ",
            "0x8004029e" : "データが書き込めない状態にある",
            "0x800402a0" : "軸指定不正",
            "0x8004024d" : "安全パスワードロック中",
            "0x800402a2" : "SRAM開放パラメータ不正によりフォーマット中止した",
            "0x800402a4" : "編集ァイルを登録できない(既に編集中)",
            "0x800402a5" : "編集ファイルを解除できない",
            "0x800402a3" : "書き込み先データなし",
            "0x8004029a" : "書き込みデータ範囲不正",
            "0x800402a6" : "安全パスワード未設定",
            "0x800402a7" : "安全データ整合性チェックエラー",
            "0x800402a9" : "安全用データタイプ不",
            "0x800402a8" : "工具データソート中で書き込みできない",
            "0x80040501" : "高速読み出し登録されていない",
            "0x80040402" : "プライオリティ指定不正",
            "0x80040401" : "登録数をオーバした",
            "0x80040490" : "アドレス不正",
            "0x80040491" : "大区分番号不正",
            "0x80040492" : "小区分番号不正",
            "0x80040497" : "データタイプ不正",
            "0x8004049b" : "読み出し専用データ",
            "0x8004049d" : "データが読み出せない状態にある",
            "0x8004049f" : "書き込み専用データ",
            "0x800404a0" : "軸指定不正",
            "0x80040ba3" : "再ねじ切り位置設定なし",
            "0x80030101" : "既に別ディレクトリがオープンされている",
            "0x80030103" : "データサイズオーバ",
            "0x80030148" : "ファイル名が長い",
            "0x80030198" : "ファイル名フォーマットが不正",
            "0x80030190" : "オープンされていない",
            "0x80030194" : "ファイル情報リードエラー",
            "0x80030102" : "すでに別ディレクトリがオープンされている(PCのみ)",
            "0x800301a0" : "オープンされていない",
            "0x800301a1" : "ファイルが存在しない",
            "0x800301a5" : "ファイル情報リードエラー",
            "0x80030447" : "コピーできない状態にある(運転中)",
            "0x80030403" : "登録本数オーバ",
            "0x80030401" : "コピー先ファイルが既に存在する",
            "0x80030443" : "ファイルシステムに異常がある",
            "0x80030448" : "ファイル名が長い",
            "0x80030498" : "ファイル名フォーマットが不正",
            "0x80030404" : "メモリ容量オーバ",
            "0x80030491" : "ディレクトリが存在しない",
            "0x8003049b" : "ドライブが存在しない",
            "0x80030442" : "ファイルが存在しない",
            "0x80030446" : "コピーできない状態にある(PLC動作中)",
            "0x80030494" : "転送元ファイルが読めない",
            "0x80030495" : "転送先ファイルに書き込めない",
            "0x8003044a" : "コピーできない状態にある(プロテクト中)",
            "0x80030405" : "照合エラー",
            "0x80030449" : "照合機能をサポートしていない",
            "0x8003044c" : "ファイルコピー中",
            "0x80030490" : "ファイルがオープンされていない",
            "0x8003044d" : "安全パスワードロック中",
            "0x8003049d" : "ファイルフォーマット不正",
            "0x8003049e" : "パスワードが異なる",
            "0x800304a4" : "ファイルが生成できない(PCのみ)",
            "0x800304a3" : "ファイルをオープンできない(PCのみ)",
            "0x80030402" : "コピー先ファイルが既に存在する",
            "0x800304a7" : "ファイル名フォーマットが不正",
            "0x800304a2" : "ディレクトリが存在しない",
            "0x800304a8" : "ドライブが存在しない",
            "0x800304a1" : "ファイルが存在しない",
            "0x800304a5" : "転送元ファイルが読めない",
            "0x800304a6" : "転送先ファイルに書き込めない",
            "0x80030406" : "ディスク容量オーバ",
            "0x800304a0" : "ファイルがオープンされていない",
            "0x80030201" : "削除できないファイル",
            "0x80030242" : "ファイルが存在しない",
            "0x80030243" : "ファイルシステムに異常がある",
            "0x80030247" : "削除できない状態にある(運転中)",
            "0x80030248" : "ファイル名が長い",
            "0x8003024a" : "ファイルが削除できない状態にある(プロテクト中)",
            "0x80030291" : "ディレクトリが存在しない",
            "0x80030298" : "ファイル名フォーマットが不正",
            "0x8003029b" : "ドライブが存在しない",
            "0x80030202" : "削除できないファイル",
            "0x800302a7" : "ファイル名フォーマットが不正",
            "0x800302a2" : "ディレクトリが存在しない",
            "0x800302a8" : "ドライブが存在しない",
            "0x800302a1" : "ファイルが存在しない",
            "0x80030301" : "新ファイル名が既に存在する",
            "0x80030342" : "ファイルが存在しない",
            "0x80030343" : "ファイルシステムに異常がある",
            "0x80030347" : "リネームできない状態にある(運転中)",
            "0x80030348" : "ファイル名が長い",
            "0x8003034a" : "リネームできない状態にある(プロテクト中)",
            "0x80030391" : "ディレクトリが存在しない",
            "0x80030398" : "ファイル名フォーマットが不正",
            "0x8003039b" : "ドライブが存在しない",
            "0x80030303" : "リネームできない",
            "0x80030305" : "新旧ファイル名が同じ",
            "0x80030302" : "新ファイル名が既に存在する",
            "0x800303a7" : "ファイル名フォーマットが不正",
            "0x800303a2" : "ディレクトリが存在しない",
            "0x800303a8" : "ドライブが存在しない",
            "0x800303a1" : "ファイルが存在しない",
            "0x80030691" : "ディレクトリが存在しない",
            "0x8003069b" : "ドライブが存在しない",
            "0x80030643" : "ファイルシステムに異常がある",
            "0x80030648" : "ファイル名が長いまたはフォーマットが不正",
            "0x800306a2" : "ディレクトリが存在しない(PCのみ)",
            "0x800306a8" : "ドライブが存在しない(PCのみ)",
            "0x80030701" : "アプリケーションが用意したバッファに入りきらない",
            "0x80030794" : "ドライブ情報リードエラー",
            "0x82020001" : "すでにオープンされている",
            "0x82020002" : "オープンされていない",
            "0x82020004" : "カードが存在しない",
            "0x82020006" : "チャンネル番号不正",
            "0x82020007" : "ファイルディスクプリタ不正",
            "0x8202000a" : "コネクトされていない",
            "0x8202000b" : "クローズされていない",
            "0x82020014" : "タイムアウト",
            "0x82020015" : "データ不正",
            "0x82020016" : "キャンセル要求により終了した",
            "0x82020017" : "パケットサイズ不正",
            "0x82020018" : "タスク終了により終了した",
            "0x82020032" : "コマンド不正",
            "0x82020033" : "設定データ不正",
            "0x80060001" : "データリードキャッシュが無効",
            "0x80060090" : "アドレス不正",
            "0x80060091" : "大区分番号不正",
            "0x80060092" : "小区分番号不正",
            "0x80060097" : "データタイプ不正",
            "0x8006009a" : "データ範囲不正",
            "0x8006009d" : "データが読み出せない状態にある",
            "0x8006009f" : "データタイプ不正",
            "0x800600a0" : "軸指定不正",
            "0x80070140" : "作業領域を確保できない",
            "0x80070142" : "ファイルをオープンできない",
            "0x80070147" : "ファイルがオープンできない状態にある(運転中)",
            "0x80070148" : "ファイルパスが長い",
            "0x80070149" : "未サポート(CF未対応)",
            "0x80070192" : "すでにオープンされている",
            "0x80070199" : "最大ファイルオープン数を越えた",
            "0x8007019f" : "工具データソート中でオープンができない",
            "0x800701b0" : "安全パスワードが未認証",
            "0x80070290" : "ファイルがオープンされていない",
            "0x80070340" : "作業領域を確保できない",
            "0x80070347" : "ファイルが生成できない状態にある(運転中)",
            "0x80070348" : "ファイルパスが長い",
            "0x80070349" : "未サポート(CF未対応)",
            "0x80070392" : "すでに生成されている",
            "0x80070393" : "ファイルを生成できない",
            "0x80070399" : "最大ファイルオープン数を越えた",
            "0x8007039b" : "ドライブが存在しない",
            "0x80070490" : "ファイルがオープンされていない",
            "0x80070494" : "ファイル情報リードエラー",
            "0x80070549" : "書き込み不可",
            "0x80070590" : "ファイルがオープンされていない",
            "0x80070595" : "ファイル書き込みエラー",
            "0x80070740" : "ファイル削除エラー",
            "0x80070742" : "ファイルが存在しない3-6",
            "0x80070747" : "ファイルが削除できない状態にある(運転中)",
            "0x80070748" : "ファイルパスが長い",
            "0x80070749" : "未サポート(CF未対応)",
            "0x80070792" : "ファイルがオープンされている",
            "0x8007079b" : "ドライブが存在しない",
            "0x80070842" : "ファイルが存在しない",
            "0x80070843" : "リネームできないファイル",
            "0x80070848" : "ファイルパスが長い",
            "0x80070849" : "未サポート(CF未対応)",
            "0x80070892" : "ファイルがオープンされている",
            "0x80070899" : "最大ファイルオープン数を越えた",
            "0x8007089b" : "ドライブが存在しない",
            "0x80070944" : "コマンド不正(未対応)",
            "0x80070990" : "オープンされていない",
            "0x80070994" : "リードエラー",
            "0x80070995" : "ライトエラー",
            "0x80070996" : "アプリケーションが用意したバッファに入りきらない",
            "0x80070997" : "データタイプ不正",
            "0x80070949" : "未サポート(CF未対応)",
            "0x80070a40" : "作業領域を確保できない",
            "0x80070a47" : "ディレクトリがオープンできない状態にある(運転中)",
            "0x80070a48" : "ファイルパスが長い",
            "0x80070a49" : "未サポート(CF未対応)",
            "0x80070a91" : "ディレクトリが存在しない",
            "0x80070a92" : "すでにオープンされている",
            "0x80070a99" : "最大ディレクトリオープン数を越えた",
            "0x80070a9b" : "ドライブが存在しない",
            "0x80070b90" : "ディレクトリがオープンされていない",
            "0x80070b91" : "ディレクトリが存在しない",
            "0x80070b96" : "アプリケーションが用意したバッファに入りきらない",
            "0x80070d90" : "ディレクトリがオープンされていない",
            "0x80070e48" : "ファイルパスが長い",
            "0x80070e49" : "サポート(CF未対応)",
            "0x80070e94" : "ファイル情報読み込みエラー",
            "0x80070e99" : "最大ファイルオープン数を越えた",
            "0x80070e9b" : "ドライブが存在しない",
            "0x80070f48" : "ファイルパスが長い",
            "0x80070f49" : "未サポート(CF未対応)",
            "0x80070f94" : "ファイル情報読み込みエラー",
            "0x80070f90" : "ファイルがオープンされていないた",
            "0x80070f9b" : "ドライブが存在しない",
            "0x8007099c" : "SRAM開放パラ不正でフォーマット中止",
            "0xf00000ff" : "引数が不正",
            "0xffffffff" : "データが読み出せない/書き込めない状態"
        }

        # 0: エラーなし, 1以上: File_FindDir2時にファイル情報ありの時
        if errcd == 0 or errcd >= 1: 
            return
        
        hex_str = '0x' + format(errcd & 0xffffffff, 'x')
        msg = __errmap.get(hex_str, 'Unkown error') # 辞書に無ければUnkown error

        # '通信回線がオープンされてない'or'コネクトされていない'ならclose扱い
        if '0x80a00101' == hex_str or '0x8202000a' == hex_str:
            self.close()
        raise Exception('Error=(IP:' + self.__ip + ') ' + hex_str + ': ' + msg)
