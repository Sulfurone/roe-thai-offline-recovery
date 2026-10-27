"""Read complete original ItemTable v1/row121 using 0x7AF140 reflection.

Arrays are bounded, only observed compact UTF-8 strings are accepted, and
all rows must end exactly at the original QSSplitTableBase footer.
"""
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='''dwStringID I
szName s
mCategory I
mSubCategory I
enumQuality I
nValueLV I
nLimitLVMin I
nLimitLVMax I
szMartialArtDemandArray vI
JobDemandArray vI
enumSexDemand I
nAllianceId I
nAllianceDutyArray vI
nSellMoneyType I
nSellCost I
nSellItem I
nSellItemNum I
enumBinding I
bTradeBound B
bDiscardAble B
bSellAble B
bMailAble B
bBankAble B
bPitchAble B
bGoldLock B
bActiveOpen B
szExplain s
szBackground s
nDropEntityId I
nMaleItemId I
nFmaleItemId I
UseCondition s
nUseNum I
nWeight f
OtherEffect s
OtherClientEffect s
enumPreProcessType I
dwSkillEffect I
dwQuestID I
BulletType I
BulletUseTypeArray vI
WeaponPartTypeCanUseArray vI
WeaponPartIndexCanUseArray vI
WeaponPartType I
WeaponPartIndex I
m_nCategoryArray vI
enumExpireType I
nExpireDuration I
ExpireCronArray vs
dwCountLimitID I
nPackMax I
nExtParamType I
nTypeParam I
nSinging I
fCDLength f
nGCDGroupIDArray vf
fGCDLengthArray vf
fGCDFactorArray vf
nJiangXinValue I
szPositionArray vI
szPositionPlaceArray vI
bSplitAble B
bEnhanceAble B
bJiangXinAble B
bTejiAble B
nEnhanceLevelMax I
enumDurable I
nDurableValue I
nDEF I
nDEFHead I
nExtWeight I
mHealValue f
szPackage2D s
szTIPS2D s
szIconL s
dwDrop3DID I
szDropEffectFileName s
szAvatar3D_b s
szAvatar3D_c s
szAvatar3D_d s
szAvatar3DNpcID_b s
szAvatar3DNpcID_c s
szAvatar3DNpcID_d s
szAvatar3D_b_variance s
szAvatar3D_d_variance s
nCoatArmorVariance I
nCoatBagVariance I
bIsAvatarOutSide B
szTypeTips s
szShopIcon s
nPower I
nRange I
nStability I
nFiringRate I
nShowPower I
nShowRange I
nShowStability I
nShowFiringRate I
nSortPriority I
enumAuctionType I
dwItemAudioId I
dwItemAudioIdName s
dwSetID I
nFurnitureType I
nFurnitureStyle I
bSellAuction B
nXinfaId I
eTipProcessType I
szSpecialExplain s
szSpecialBackground s
enumOpenUIType I
szFromWhere s
szHowToUse s
eEquipType I
nFarmTypeRequireArray vI
nFarmBelongerTypeRequireArray vI
nCropColorRatioLowArray vI
nCropColorRatioMediumArray vI
nCropColorRatioHighArray vI
dwSMBPanelId I
sSMBContentScript s'''
FIELDS=[line.split() for line in SCHEMA.splitlines()]
if len(FIELDS)!=121:raise ValueError(f'Wrong recovered field count: {len(FIELDS)}')

class Reader:
    def __init__(self,blob):self.blob,self.pos=blob,0
    def value(self,kind):
        if kind.startswith('v'):
            count=self.value('I')
            if count>256:raise ValueError('Array exceeds original item extraction bound')
            return [self.value(kind[1:]) for _ in range(count)]
        if kind=='s':
            tag=self.value('B')
            if tag>=0xc0:
                length=tag&0x3f
            elif tag>=0x80:
                length=(tag&0x3f)|(self.value('B')<<6)
                if length<64:raise ValueError('Noncanonical two-byte compact length')
            else:raise ValueError(f'Unknown compact string {tag:#x} at {self.pos-1}')
            if length>4096:raise ValueError('Item text exceeds extraction bound')
            if self.pos+length>len(self.blob):raise ValueError('Truncated item string')
            value=self.blob[self.pos:self.pos+length].decode('utf-8')
            self.pos+=length
            return value
        size=struct.calcsize('<'+kind)
        if self.pos+size>len(self.blob):raise ValueError('Truncated item field')
        value=struct.unpack_from('<'+kind,self.blob,self.pos)[0]
        self.pos+=size
        return value

def extract(path):
    blob=path.read_bytes()
    header=b'\x09ItemTable'*2
    if not blob.startswith(header):raise ValueError('Wrong ItemTable header')
    reader=Reader(blob)
    reader.pos=len(header)
    if reader.value('H')!=1:raise ValueError('Unknown table version')
    count=reader.value('I')
    if not 0<count<=2048:raise ValueError('Unexpected item count')
    rows=[]
    for _ in range(count):
        start=reader.pos
        if reader.value('H')!=121:raise ValueError(f'Wrong row121 boundary {start}')
        row={}
        for name,kind in FIELDS:
            try:row[name]=reader.value(kind)
            except (ValueError,UnicodeDecodeError) as error:
                raise ValueError(f'{path.name}, row at {start}, field {name}: {error}') from error
        row.update(start=start,end=reader.pos)
        rows.append(row)
    if blob[reader.pos:reader.pos+17]!=b'\x10QSSplitTableBase':
        raise ValueError(f'Item rows do not end at original footer: {reader.pos}')
    ids=[row['dwStringID'] for row in rows]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate item ID within original table')
    return dict(source=path.name,source_sha256=hashlib.sha256(blob).hexdigest(),
        reflection='0x7AF140',row_count=count,rows_end=reader.pos,rows=rows)

def main():
    tables=[extract(ROOT/'extracted/tablebin'/name) for name in
        ('4049c7809f4ac10f.bin','08e66a956e5d5647.bin','83802c700bde8442.bin')]
    wanted={10101,10201,10202,10203,10204,10205,10207,10301,10302,10303,10401,10402,10403,30001,30002,30003,30004,30005,30006}
    keys=('dwStringID','szName','mCategory','mSubCategory','BulletType','BulletUseTypeArray','nPackMax','mHealValue')
    selected=[dict(source=table['source'],**{key:row[key] for key in keys})
        for table in tables for row in table['rows'] if row['dwStringID'] in wanted]
    destination=ROOT/'private/gameplay-catalog/original-item-defaults.json'
    destination.write_text(json.dumps({'tables':tables,'selected_items':selected},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'tables':[{k:t[k] for k in ('source','row_count','rows_end')} for t in tables],
                      'selected_items':selected},ensure_ascii=True,indent=2))

if __name__=='__main__':main()
