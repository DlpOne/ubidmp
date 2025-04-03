#!/usr/bin/python

import struct
import sys

def parseEreaseHeader(f):
    '''
    struct erease_block{
    u32 magic;
    u8 version;
    u8 padding1[3];
    u64 ec;
    u32 vid_hdr_offset; // position des volume header
    u32 data_offset; //beginn der daten, diese befinden sich unterhalb des volume header
    u8 padding2[36];
    u32 hdr_crc;
    };
    '''
    data=f.read(64)

    magic=data[0:4]
    version=data[4]
    ec,vid_hdr_offset,data_offset=struct.unpack('>QII',data[8:24])
    hdr_crc=struct.unpack('>I',data[60:64])

    return {
        'Magic':magic,
        'versions':version,
        'ec':ec,
        'vid_hdr_offset':vid_hdr_offset,
        'data_offset':data_offset,
        'hdr_crc':hdr_crc
    }

def parseVolumeHeader(f):
    '''
    struct ubi_vid_hdr {
        u32 magic;
        u8 version;
        u8 vol_type;
        u8 copy_flag;
        u8 compat;
        u32 vol_id;
        u32 lnum;
        u32 leb_ver;
        u32 data_size;
        u32 used_ebs;
        u32 data_pad;
        u32 data_crc;
        u8 padding1[12];
        u8 ivol_data[12];
        u32 hdr_crc;
    };
    '''
    data=f.read(64)
    magic=data[0:4]
    version,vol_type,copy_flag,compat,vol_id,lnum,leb_ver,data_size,used_ebs,data_pad,data_crc=struct.unpack('>BBBBIIIIIII',data[4:36])
    hdr_crc=struct.unpack('>I',data[60:64])
                          
    return {
        'magic':magic,
        'version':version,
        'vol_type':vol_type,
        'copy_flag':copy_flag,
        'compat':compat,
        'vol_id':vol_id,
        'lnum':lnum,
        'leb_ver':leb_ver,
        'data_size':data_size,
        'used_ebs':used_ebs,
        'data_pad':data_pad,
        'data_crc':data_crc,
        'hdr_crc':hdr_crc
    }

def parseVTblRecord(f):
    vtblrecords=list()
    '''
    struct ubi_vtbl_record {
        __be32  reserved_pebs;
        __be32  alignment;
        __be32  data_pad;
        __u8    vol_type;
        __u8    upd_marker;
        __be16  name_len;
        __u8    name[UBI_VOL_NAME_MAX+1];
        __u8    flags;
        __u8    padding[23];
        __be32  crc;
    } __packed;
    '''
    for i in range(128):
        data=f.read(172)
        reserved_pebs,alignment,data_pd,vol_type,upd_marker,name_len=struct.unpack('>IIIBBH',data[:16])
        name=data[16:16+name_len].decode('UTF-8')
        flags=data[16+128]
        crc=struct.unpack('>I',data[16+24+128:172])
        tblrecord={
            'reserved_pebs':reserved_pebs,
            'vol_type':vol_type,
            'upd_marker':upd_marker,
            'name_len':name_len,
            'name':name,
            'flags':flags,
            'crc':crc
        }
        vtblrecords.append(tblrecord)

    return vtblrecords

def readDynamicVolumeData(f):
    data=b''

    temp=f.read(3)
    while True:
        temp+=f.read(1)
        
        if not temp:
            break
        
        if temp == b"UBI#":
            f.seek(-4,1)
            break
        else:
            data+=temp[0:1]
            temp=temp[1:]

    return data

def parseUbiBlock(f):

    ubiBlock=dict()

    ereaseHeader=parseEreaseHeader(f)
    ubiBlock['ereaseHeader']=ereaseHeader


    f.seek(ereaseHeader['vid_hdr_offset']-64,1)

    volumeHeader=parseVolumeHeader(f)
    ubiBlock['volumeHeader']=volumeHeader


    f.seek(ereaseHeader['data_offset']-ereaseHeader['vid_hdr_offset']-64,1)

    print (f"volume type {volumeHeader['vol_id']}")
    if volumeHeader['vol_id'] == 2147479551:
        print ("VtableRecord found: ")
        vtblrecords=parseVTblRecord(f)
        ubiBlock['vtableRecords']=vtblrecords
    else:
        data=b''
        if volumeHeader['vol_type']==2:
            data=f.read(volumeHeader['data_size'])
        else:
            data=readDynamicVolumeData(f)    
        ubiBlock['data']=data


    return ubiBlock

 
def main(filename):

    ubiblocks=list()
    vtablesRecords=dict()

    print (f"Parsing UBI Image file {filename}")

    with open(filename, "rb") as f:
        data=f.read(3)

        while True:
            data+=f.read(1)
            
            if not data:
                break
            
            if data==b'UBI#' :
                f.seek(-4,1)
                print(f"UBIBLOCK found at {f.tell()}")
                ubiblocks.append(parseUbiBlock(f))
                data=f.read(3)
            else:
                data=data[1:]

    
    print (f"{len(ubiblocks)} found")

    for ubiblock in ubiblocks:
        if 'vtableRecords' in ubiblock.keys():
            for i in range(128):
                vtableRecord=ubiblock['vtableRecords'][i]

                if len(vtableRecord['name'])>0:
                    blckcount=0
                    
                    for _ubiblock in ubiblocks:
                        volumeHeader=_ubiblock['volumeHeader']
                        if volumeHeader['vol_id'] == i and volumeHeader['lnum'] > blckcount:
                            blckcount=volumeHeader['lnum']

                    blckcount+=1
                    vtablesRecords[vtableRecord['name']]={'id':i,'blckcount':blckcount}

                    print (f"Vtable Volume: {vtableRecord['name']} id: {i} blockcount: {blckcount}")




        break #we only need to parse the first vtableresocrd volume 

    prefix="dmp_"

    for ubiname in vtablesRecords.keys():
        vtablesRecord=vtablesRecords[ubiname]
        with open(prefix+ubiname, "wb") as f:
            for blockid in range(vtablesRecord['blckcount']):
                for ubiblock in ubiblocks:
                    volumeHeader=ubiblock['volumeHeader']
                    if (volumeHeader['vol_id']==vtablesRecord['id']and blockid==volumeHeader['lnum']):
                        f.write(ubiblock['data'])
                        print(f"write Ubiblock {blockid} for {vtablesRecord['id']} to {prefix+ubiname}\n ")
                        break
            
            f.close()

          

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage {sys.argv[0]} <firmwarefile>")

    main(sys.argv[1])
