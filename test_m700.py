# coding: utf-8
'''
本テストは三菱M700のテストスクリプトです。

※注意　デバイスの操作によって、物理的な機械が動く可能性があります。
      必ず安全を確かめ、テストコード内の操作を理解した上で実行して下さい。
'''
import os
import sys
import unittest

from m700 import M700


class TestM700(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        '''テストクラスが初期化される際に一度だけ呼ばれる。'''
        print('----- TestM700 start ------')
        cls.m700 = M700.get_connection('192.168.48.173:683')

    @classmethod
    def tearDownClass(cls):
        '''テストクラスが解放される際に一度だけ呼ばれる。'''
        cls.m700.close()
        print('----- TestM700 end ------')

    def setUp(self):
        '''テストごとに開始前に必ず実行'''
        if not self.m700.is_open():
            self.skipTest('指定されたIPに接続できません。電源が入っていない可能性があります。')

    def test_result_type(self):
        '''内部情報を取得し、各メソッドが返す型が正常かテスト。
        
        値はその時々で変わる為、正常に実行できるかどうかのみのチェックで良しとする。
        '''
        self.assertIs(type(self.m700.get_drive_infomation()), str)
        self.assertIs(type(self.m700.get_version()), str)
        self.assertIs(type(self.m700.get_current_position(M700.Position.X)), float)
        self.assertIs(type(self.m700.get_run_status()), M700.RunStatus)
        self.assertIs(type(self.m700.get_rpm()), int)
        self.assertIs(type(self.m700.get_load()), int)
        self.assertIs(type(self.m700.get_mgn_size()), int)
        self.assertIs(type(self.m700.get_mgn_ready()), int)
        self.assertIs(type(self.m700.get_toolset_size()), int)
        self.assertIs(type(self.m700.get_program_number(M700.ProgramType.MAIN)), str)
        self.assertIs(type(self.m700.get_alerm()), str)

    def test_operate_program_file(self):
        '''加工プログラム読み書きテスト。'''
        drivenm = self.m700.get_drive_infomation()
        self.m700.write_file(drivenm + '¥PRG¥USER¥__TEST__.txt', b'TEST_WRITE')
        self.assertEqual(self.m700.read_file(drivenm + '¥PRG¥USER¥__TEST__.txt'), b'TEST_WRITE')
        self.m700.delete_file(drivenm + '¥PRG¥USER¥__TEST__.txt')

    def test_dev_operation(self):
        '''M,Dデバイスの読み書きテスト。'''
        self.m700.write_dev('M900', 1)
        self.assertEqual(self.m700.read_dev('M900'), 1)
        self.m700.write_dev('M900', 0)
        self.assertEqual(self.m700.read_dev('M900'), 0)
        self.m700.write_dev('D200', 10)
        self.assertEqual(self.m700.read_dev('D200'), 10)
        self.m700.write_dev('D200', 0)
        self.assertEqual(self.m700.read_dev('D200'), 0)
            
if __name__ == '__main__':
    unittest.main()
