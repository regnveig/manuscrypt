import bitarray #
import json
import numpy #
import os

def MonogramLoad():
	MonogramFontJson = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'fonts', 'monogram-bitmap.json')
	with open(MonogramFontJson, 'rt') as f: Dict = json.load(f)
	for Char in Dict:
		CharMatrix = list()
		for LineInt in Dict[Char]:
			Row = bitarray.bitarray(endian = 'little')
			Row.frombytes(LineInt.to_bytes(1, byteorder = 'little'))
			CharMatrix.append([int(item) for item in Row.to01()])
		Dict[Char] = numpy.array(CharMatrix, dtype = numpy.int8)
	Dict['__tofu__'] = numpy.zeros((12, 8), dtype = numpy.int8)
	Dict['__tofu__'][3:10, 0:5] = 1
	return Dict

def MonogramWriteRow(Row, MonogramDict):
	Chars = list()
	for item in Row:
		try:
			Chars.append(MonogramDict[item])
		except KeyError:
			Chars.append(MonogramDict['__tofu__'])
	RowMatrix = numpy.concatenate(Chars, axis = 1)
	return RowMatrix
