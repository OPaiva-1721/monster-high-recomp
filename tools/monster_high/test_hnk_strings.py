import struct
import unittest
from hnk_strings import catalogue, chunks, rebuild, tables, heap_budgets

def fixture():
    meta=b'PREFIXStringTable\0Dialog\0'
    p=bytearray(struct.pack('>III',1,2,2)+struct.pack('<II',28,36)+b'\0'*8)
    p.extend(struct.pack('>II',44,50))
    p.extend(struct.pack('>II',0x1234,0x9876))
    p.extend(b'Hello\0Yes\0')
    pack=lambda kind,payload:struct.pack('<II',len(payload),kind)+payload
    root=bytearray(592)
    struct.pack_into('<I',root,12,2)
    struct.pack_into('<I',root,80,11)
    struct.pack_into('<I',root,152,len(p))
    return pack(0x40070,root)+pack(0x40071,meta)+pack(0x4100F,p)+pack(0x40002,b'relocations')

class HnkTests(unittest.TestCase):
    def test_noop_is_byte_identical(self):
        data=fixture();self.assertEqual(rebuild(data,catalogue(data)),data)

    def test_reject_inconsistent_allocation_budget(self):
        data=bytearray(fixture());struct.pack_into('<I',data,160,1)
        with self.assertRaises(ValueError):rebuild(bytes(data),catalogue(bytes(data)))

    def test_long_translation_keeps_ids_and_other_chunks(self):
        data=fixture();cat=catalogue(data)
        cat['entries'][0]['translation']='Olá! Você chegou à escola; faça novas amizades.'
        output=rebuild(data,cat)
        self.assertGreater(len(output),len(data))
        entries=list(tables(output))[0][-1]
        self.assertEqual(entries[0]['source'],cat['entries'][0]['translation'])
        self.assertEqual(entries[1],{'id':'00009876','source':'Yes'})
        before=list(chunks(data));after=list(chunks(output))
        self.assertEqual([x[1:] for i,x in enumerate(before) if i not in (0,2)], [x[1:] for i,x in enumerate(after) if i not in (0,2)])
        self.assertEqual(heap_budgets(output)[0],heap_budgets(output)[1])

    def test_reject_unknown_source_and_truncated_chunk(self):
        data=fixture();cat=catalogue(data);cat['entries'][0]['source']='wrong'
        with self.assertRaises(ValueError):rebuild(data,cat)
        with self.assertRaises(ValueError):list(chunks(data[:-1]))
        cat=catalogue(data);cat['entries'][0]['id']='DEADBEEF'
        with self.assertRaises(ValueError):rebuild(data,cat)

    def test_shared_suffix_is_preserved_by_id(self):
        data=fixture();records=list(chunks(data));pos,kind,payload=records[2]
        payload=bytearray(payload)
        struct.pack_into('>I',payload,32,47)  # second ID points at "lo" inside "Hello"
        data=data[:pos]+struct.pack('<II',len(payload),kind)+payload+data[pos+8+len(payload):]
        cat=catalogue(data)
        self.assertEqual(cat['entries'][1]['source'],'lo')
        cat['entries'][0]['translation']='Uma frase bem maior que a original.'
        restored=catalogue(rebuild(data,cat))
        self.assertEqual(restored['entries'][1]['source'],'lo')

if __name__=='__main__':unittest.main()
