// packreader.js — 零依赖 ZIP 读取器（B02 手机语料包）。
// 只支持 STORED 条目：server/pack.py 导出时全部 ZIP_STORED（mp3 本就不可压缩），
// 因此无需实现 inflate，移动端零依赖即可解包。
// 用法：const files = parsePackZip(arrayBuffer) → Map<name, {getText(), getBytes(), getBlob()}>
"use strict";

function parsePackZip(buffer) {
  const dv = new DataView(buffer);
  const u8 = new Uint8Array(buffer);
  const decoder = new TextDecoder();

  // 1) 从尾部扫描 End Of Central Directory 记录（签名 0x06054b50，最短 22 字节）
  const minEocd = buffer.byteLength - 22;
  let eocd = -1;
  for (let i = minEocd; i >= 0 && i >= minEocd - 65536; i--) {
    if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error("不是有效的语料包（找不到 zip 目录）");

  // 2) 解析 central directory：每项拿 文件名/大小/本地头偏移
  const count = dv.getUint16(eocd + 10, true);
  let ptr = dv.getUint32(eocd + 16, true);
  const files = new Map();
  for (let n = 0; n < count; n++) {
    if (dv.getUint32(ptr, true) !== 0x02014b50) throw new Error("语料包目录损坏");
    const method = dv.getUint16(ptr + 10, true);
    const size = dv.getUint32(ptr + 24, true); // stored：压缩后=原始大小
    const nameLen = dv.getUint16(ptr + 28, true);
    const extraLen = dv.getUint16(ptr + 30, true);
    const commentLen = dv.getUint16(ptr + 32, true);
    const localOff = dv.getUint32(ptr + 42, true);
    const name = decoder.decode(u8.subarray(ptr + 46, ptr + 46 + nameLen));
    if (name.endsWith("/")) { ptr += 46 + nameLen + extraLen + commentLen; continue; }
    if (method !== 0) throw new Error(`包内条目被压缩（${name}）——只支持 STORED 语料包`);
    files.set(name, { _localOff: localOff, _size: size });
    ptr += 46 + nameLen + extraLen + commentLen;
  }

  // 3) 本地头里再读一次 nameLen/extraLen 才是真实数据区偏移
  for (const ent of files.values()) {
    const off = ent._localOff;
    if (dv.getUint32(off, true) !== 0x04034b50) throw new Error("语料包条目损坏");
    const lhNameLen = dv.getUint16(off + 26, true);
    const lhExtraLen = dv.getUint16(off + 28, true);
    const dataStart = off + 30 + lhNameLen + lhExtraLen;
    const dataEnd = dataStart + ent._size;
    ent.getBytes = () => u8.slice(dataStart, dataEnd);
    ent.getText = () => decoder.decode(ent.getBytes());
    ent.getBlob = () => new Blob([u8.slice(dataStart, dataEnd)]);
    delete ent._localOff;
    delete ent._size;
  }
  return files;
}

if (typeof window !== "undefined") window.parsePackZip = parsePackZip;
