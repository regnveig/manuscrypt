import bitarray #
import itertools
import json
import math
import numpy #
import os
import qrcode #
import random
import sys

from font import *

# Load QR const
AlignPatternsJson = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'qr_const', 'align_patterns.json')
DataBlocksJson = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'qr_const', 'data_blocks.json')
with open(AlignPatternsJson, 'rt') as f: AlignPatterns = json.load(f)
with open(DataBlocksJson, 'rt') as f: DataBlocks = json.load(f)

# Primitive visualization [debug]

def PrintMatrix(Matrix):
	Size = Matrix.shape[0]
	sys.stdout.write("\x1b[1;47m" + (" " * (Size * 2 + 4)) + "\x1b[0m\n")
	for Row in range(Matrix.shape[0]):
		sys.stdout.write("\x1b[1;47m  \x1b[40m")
		for Col in range(Matrix.shape[1]):
			if Matrix[Row][Col]: sys.stdout.write("  ")
			else: sys.stdout.write("\x1b[1;47m  \x1b[40m")
		sys.stdout.write("\x1b[1;47m  \x1b[0m\n")
	sys.stdout.write("\x1b[1;47m" + (" " * (Size * 2 + 4)) + "\x1b[0m\n")
	sys.stdout.flush()

# Alphanumeric encoding

def BitstringToAlphanumeric(Bitstring):
	AlphanumericString = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
	Result = list()
	for it in range(0, len(Bitstring), 11):
		Chunk = Bitstring[it:it + 11]
		Chunk = bitarray.bitarray('0' * (16 - len(Chunk))) + Chunk
		Int = int.from_bytes(Chunk.tobytes(), 'big')
		try:
			NewChunk = str()
			NewChunk += AlphanumericString[Int // 45]
			NewChunk += AlphanumericString[Int % 45]
		except IndexError:
			# TODO Optimized adding instead of zero!
			NewChunk = '00'
		Result.append(NewChunk)
	return ''.join(Result)

# Mask funcs

MaskFunc = {
	0: lambda i, j: (i + j) % 2 == 0,
	1: lambda i, j: i % 2 == 0,
	2: lambda i, j: j % 3 == 0,
	3: lambda i, j: (i + j) % 3 == 0,
	4: lambda i, j: (math.floor(i / 2) + math.floor(j / 3)) % 2 == 0,
	5: lambda i, j: (i * j) % 2 + (i * j) % 3 == 0,
	6: lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0,
	7: lambda i, j: ((i * j) % 3 + (i + j) % 2) % 2 == 0
}

# QR Layout

def MakeLayout(Version, ErrorCorrection):
	Result = dict()
	# Make layout
	Size = (4 * Version) + 17
	InfoLayout = numpy.zeros((Size, Size), dtype = numpy.int8)
	# Make sync lines
	InfoLayout[6, ::] = 1
	InfoLayout[::, 6] = 1
	# Make place
	InfoLayout[:9:, :9:] = 1
	InfoLayout[:9:, -8::] = 1
	InfoLayout[-8::, :9:] = 1
	if Version >= 7:
		InfoLayout[:6:, -11::] = 1
		InfoLayout[-11::, :6:] = 1
	# Make align patterns
	Points = AlignPatterns[str(Version)]
	Banned = list() if not Points else [ (Points[a], Points[b]) for a, b in [ (0, 0), (0, -1), (-1, 0) ] ]
	for Coords in itertools.product(Points, repeat = 2):
		if Coords in Banned: continue
		InfoLayout[Coords[0] - 2:Coords[0] + 3, Coords[1] - 2:Coords[1] + 3] = 1
	return InfoLayout

def MakeBitPositions(InfoLayout, Version, ErrorCorrection):
	Size = (4 * Version) + 17
	Bits = list()
	StartIs = [1,3,5] + list(range(8, Size, 2))
	StartIs = [(i, True) if (len(StartIs) - index) % 2 == 1 else (i, False) for index, i in enumerate(StartIs) ]
	StartIs.reverse()
	for ColInfo in StartIs:
		Col, Reverse = ColInfo
		Rows = list(range(Size))
		if Reverse: Rows.reverse()
		for Row in Rows: Bits.extend([(Row, Col), (Row, Col - 1)])
	Bits = [item for item in Bits if not InfoLayout[item[0]][item[1]]]
	BlockData = DataBlocks[str(Version)][ErrorCorrection]
	Blocks = (([BlockData['Total'] // BlockData['Blocks']] * (BlockData['Blocks'] - (BlockData['Total'] % BlockData['Blocks']))) +
			([BlockData['Total'] // BlockData['Blocks'] + 1] * (BlockData['Total'] % BlockData['Blocks'])))
	BlockList = []
	for stepi in range(BlockData['Total'] // BlockData['Blocks'] + 1):
		for stepj in range(BlockData['Blocks']):
			if (stepi == (BlockData['Total'] // BlockData['Blocks'])) and (stepj < (BlockData['Blocks'] - (BlockData['Total'] % BlockData['Blocks']))): continue
			BlockList.append(sum(Blocks[:stepj]) + stepi)
	BitsBlocks = []
	for i in BlockList: BitsBlocks.extend([(i*8)+k for k in range(8)])
	
	BitsDict = { b: c for b, c in enumerate(Bits[4:]) }
	BitDict = dict(sorted([(b, BitsDict[a]) for a, b in enumerate(BitsBlocks[4:])]))
	return BitDict

def MakeQR(Version, MaskPattern, ErrorCorrection):
	Layout = MakeLayout(Version, ErrorCorrection)
	DrawLayout = numpy.zeros(Layout.shape, dtype = numpy.int8)
	MonogramDict = MonogramLoad()
	Sign = MonogramWriteRow('Hello dear', MonogramDict)
	Sign = numpy.rot90(Sign, 3)
	x, y = 65,9
	DrawLayout[y:y+Sign.shape[0], x:x+Sign.shape[1]] = Sign
	x, y = 77,9
	DrawLayout[y:y+Sign.shape[0], x:x+Sign.shape[1]] = Sign
	BitPositions = MakeBitPositions(Layout, Version, ErrorCorrection)
	BitString = bitarray.bitarray(endian = 'big')
	Mask = MaskFunc[MaskPattern]
	BitLine = list(BitPositions.values())
	Img = []
	for i in BitLine[11:-10]:
		if (not DrawLayout[i[0], i[1]]):
			BitString.append( 1 if Mask(i[0], i[1]) else 0)
		else:
			BitString.append( 0 if Mask(i[0], i[1]) else 1)
	# Encode data and prepare for QR
	AlphaString = BitstringToAlphanumeric(BitString)
	DataObject = qrcode.util.QRData(AlphaString, mode = 2, check_data = True)
	# Create QR
	QR = qrcode.QRCode(version = Version, error_correction = qrcode.constants.ERROR_CORRECT_L, mask_pattern = MaskPattern, border = 0)
	QR.add_data(DataObject, optimize = 0)
	QR.make(fit = False)
	# Extract the matrix
	Matrix = numpy.array(QR.get_matrix())
	Matrix = numpy.vectorize(lambda x: int(x))(Matrix)
	return numpy.array(Matrix, dtype = numpy.int8)

m = MakeQR(20, 0, 'L')
m = numpy.rot90(m)
PrintMatrix(m)
