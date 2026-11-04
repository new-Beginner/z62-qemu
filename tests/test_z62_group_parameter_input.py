"""Virtual input integrity and numerical declarations, without QEMU/camera IO."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import create_z62_group_parameter_input as profile


class GroupParameterInputTests(unittest.TestCase):
    def baseline(self):
        data=bytearray(0x20000);data[-4:]=b'ENDM';data[4]=0x5a
        return bytes(data)

    def test_diagnostic_tag_is_the_only_changed_word(self):
        source=self.baseline();actual=profile.transform(source,'marker')
        changed=[i for i,(a,b) in enumerate(zip(source,actual)) if a!=b]
        self.assertEqual(changed,[profile.BASE+profile.CURVE+34,profile.BASE+profile.CURVE+35])
        self.assertEqual(struct.unpack_from('<H',actual,changed[0])[0],0x123)

    def test_reference_curve_and_signed_filter_variants(self):
        result=profile.transform(self.baseline(),'reference')
        self.assertEqual(struct.unpack_from('<65H',result,profile.BASE+profile.CURVE),tuple(min(i*1024,65535) for i in range(65)))
        for offset in profile.COEFFICIENTS:
            values=struct.unpack_from('<24i',result,profile.BASE+offset)
            for row in range(3):
                taps=values[row*8:(row+1)*8]
                self.assertEqual(taps[3],1);self.assertEqual(taps[4+row],-1)
                self.assertEqual(sum(abs(v) for v in taps),2)

    def test_all_other_bytes_and_trailer_are_preserved(self):
        source=self.baseline();result=profile.transform(source,'reference')
        allowed=set(range(profile.BASE+profile.CURVE,profile.BASE+profile.CURVE+130))
        for offset in profile.COEFFICIENTS:allowed.update(range(profile.BASE+offset,profile.BASE+offset+96))
        self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(source,result)) if i not in allowed))
        self.assertEqual(result[-4:],b'ENDM')

    def test_nonzero_real_or_already_transformed_resource_is_rejected(self):
        data=bytearray(self.baseline());data[profile.BASE]=1
        with self.assertRaises(ValueError):profile.transform(data,'reference')
        with self.assertRaises(ValueError):profile.transform(profile.transform(self.baseline(),'marker'),'reference')

    def test_wrong_extent_trailer_or_mode_rejected(self):
        for data,mode in ((b'','marker'),(self.baseline()[:-1],'reference'),
                (self.baseline()[:-4]+b'FAIL','marker'),(self.baseline(),'implicit')):
            with self.subTest(mode=mode),self.assertRaises(ValueError):profile.transform(data,mode)


if __name__=='__main__':unittest.main()
