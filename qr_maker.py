import bitarray #
import itertools
import json
import math
import more_itertools
import numpy #
import os
import qrcode #
import random
import sys
import logging
from font import *
import cv2 #
import datetime
import io
import itertools
import logging
import numpy #
from reportlab.graphics import renderPDF #
from reportlab.lib.units import mm #
from reportlab.pdfgen import canvas #
from svglib.svglib import svg2rlg #
import tqdm #
import gnupg

# -----=====| LOGGING |=====-----

logging.basicConfig(format='[%(levelname)s] %(message)s', level = logging.DEBUG)

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
			Int = Int % (45 ** 2)
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

def CheckBelt(X, Version):
	if not AlignPatterns[Version]: return False
	if X < AlignPatterns[Version][1]: return True
	if X > AlignPatterns[Version][-1]: return True
	for Coord in AlignPatterns[Version][1:]:
		if (Coord - 3) < X < (Coord + 3): return True
	return False

def MakeQR(TextList, Version, MaskPattern, ErrorCorrection, RunID, BlockNumber, Odd = False):
	Layout = MakeLayout(Version, ErrorCorrection)
	DrawLayout = numpy.zeros(Layout.shape, dtype = numpy.int8)
	MonogramDict = MonogramLoad()
	for Coord, Text in zip([134, 124, 106, 96, 78, 68, 50, 40], TextList):
		Sign = MonogramWriteRow(Text, MonogramDict)[:, :-2]
		if Odd: Sign = numpy.flip(Sign, axis = 1)
		Sign = numpy.rot90(Sign, 3)
		x, y = Coord, 15
		DrawLayout[y:y+Sign.shape[0], x:x+Sign.shape[1]] = Sign
	DrawLayout[y:y+Sign.shape[0], x:x+Sign.shape[1]] = Sign
	BitPositions = MakeBitPositions(Layout, Version, ErrorCorrection)
	BitString = bitarray.bitarray(endian = 'big')
	Mask = MaskFunc[MaskPattern]
	BitLine = list(BitPositions.values())
	Img = []
	for i in BitLine[13:-10]:
		if CheckBelt(i[1], str(Version)):
			BitString.append(0)
			continue
		if (not DrawLayout[i[0], i[1]]):
			BitString.append( 1 if Mask(i[0], i[1]) else 0)
		else:
			BitString.append( 0 if Mask(i[0], i[1]) else 1)
	# Encode data and prepare for QR
	AlphaString = BitstringToAlphanumeric(BitString)
	AlphaString = RunID + ('O' if Odd else 'E') + BlockNumber + AlphaString[9:]
	DataObject = qrcode.util.QRData(AlphaString, mode = 2, check_data = True)
	# Create QR
	QR = qrcode.QRCode(version = Version, error_correction = qrcode.constants.ERROR_CORRECT_L, mask_pattern = MaskPattern, border = 0)
	QR.add_data(DataObject, optimize = 0)
	QR.make(fit = False)
	# Extract the matrix
	Matrix = numpy.array(QR.get_matrix())
	Matrix = numpy.vectorize(lambda x: int(x))(Matrix)
	Result = numpy.rot90(numpy.array(Matrix, dtype = numpy.int8))
	if Odd: Result = numpy.flip(Result, axis = 1)
	return Result, AlphaString

# ArUco Marker
def KittyPawprint(ArUcoIndex, Dictionary, SpacingSize):
	Matrix = cv2.aruco.Dictionary_get(Dictionary).drawMarker(ArUcoIndex, SpacingSize)
	Matrix = numpy.vectorize(lambda x: int(not bool(x)))(Matrix)
	return Matrix

def MatrixToPixels(Matrix):
	PixelCoordinates = itertools.product(range(Matrix.shape[0]), range(Matrix.shape[1]))
	Result = [ (X, Y) for Y, X in PixelCoordinates if Matrix[Y][X] ]
	return Result

def DrawSvg(PixelSheets, PdfPageWidth, PdfPageHeight, PdfLeftMargin, PdfRightMargin, PdfTopMargin, TqdmAscii):
	SvgPages = list()
	DrawingWidth = PixelSheets[0].shape[1]
	ContentWidth = PdfPageWidth - PdfLeftMargin - PdfRightMargin
	PixelSize = ContentWidth / DrawingWidth
	logging.debug(f'Pixel Size: {PixelSize:.3f} mm')
	for PageNumber, PageMatrix in enumerate(PixelSheets):
		# Create Pixels
		Page = MatrixToPixels(PageMatrix)
		# Draw page
		SvgPage = [
			f'<svg width="{PdfPageWidth}mm" height="{PdfPageHeight}mm" viewBox="0 0 {PdfPageWidth} {PdfPageHeight}" version="1.1" xmlns="http://www.w3.org/2000/svg">',
			f'<path style="fill:#000000;stroke:none;fill-rule:evenodd" d="'
			]
		Paths = list()
		# Add Pixels
		for X, Y in tqdm.tqdm(
			Page,
			total = len(Page),
			desc = f'Draw pixels, page {PageNumber + 1} of {len(PixelSheets)}',
			ascii = TqdmAscii):
			Paths.append(f'M {PdfLeftMargin + (X * PixelSize):.3f},{PdfTopMargin + (Y * PixelSize):.3f} H {PdfLeftMargin + ((X + 1) * PixelSize):.3f} V {PdfTopMargin + ((Y + 1) * PixelSize):.3f} H {PdfLeftMargin + (X * PixelSize):.3f} Z')
		SvgPage.append(f' '.join(Paths))
		SvgPage.append(f'">')
		SvgPage.append(f'</svg>')
		# Merge svg
		SvgPages.append(''.join(SvgPage))
	return SvgPages

def CreatePixelSheets(Text, CharNum, LineNum, ColNum, RowNum, SpacingSize, DotSpacing, QRVersion, QRErrorCorrection, ArUcoDict, TqdmAscii):
	PawSize = (4 * QRVersion) + 17
	CellSize = PawSize + SpacingSize
	PageWidth = CellSize * ColNum + SpacingSize
	PageHeight = CellSize * RowNum + SpacingSize
	# Create output list
	Result = list()
	# Chunk codes to rows and pages
	Codes = list()
	EvenCode, OddCode = list(), list()
	for Index, Line in enumerate([Text[i:i + CharNum] for i in range(0, len(Text), CharNum)]):
		if Index % 2 == 0: EvenCode.append(Line.ljust(CharNum, ' '))
		else: OddCode.append(Line.ljust(CharNum, ' '))
		if len(OddCode) == LineNum:
			Codes.append(EvenCode)
			Codes.append(OddCode)
			EvenCode, OddCode = list(), list()
	if 0 < len(OddCode) < LineNum:
		EvenCode.extend([' '] * (LineNum - len(EvenCode)))
		OddCode.extend([' '] * (LineNum - len(OddCode)))
		Codes.append(EvenCode)
		Codes.append(OddCode)
		EvenCode, OddCode = list(), list()
	PageData = list(more_itertools.sliced(list(more_itertools.sliced(Codes, ColNum)), RowNum))
	SignableData = list()
	for PageNumber, Page in enumerate(PageData):
		# Create page
		Matrix = numpy.zeros((PageHeight, PageWidth))
		for Row, Col in tqdm.tqdm(
			itertools.product(range(RowNum), range(ColNum)),
			total = sum([len(item) for item in Page]),
			desc = f'Create pawprints, page {PageNumber + 1} of {len(PageData)}',
			ascii = TqdmAscii
		):
			try:
				# Create pawprint on the page
				StartX = (SpacingSize * 2) + (CellSize * Col)
				StartY = (SpacingSize * 2) + (CellSize * Row)
				Pawprint, DataString = MakeQR(Page[Row][Col], QRVersion, 0, 'L', 'DEAD', 'BEEF', Odd = Col % 2)
				SignableData.append(DataString)
				Matrix[StartY:StartY + PawSize, StartX:StartX + PawSize] = Pawprint
			except IndexError:
				# If there are no codes left
				break
		# Create dot margin (beauty, no functionality)
		#DotCentering = math.floor(SpacingSize / 2)
		#Matrix[DotCentering, SpacingSize + 2::DotSpacing] = 1
		#Matrix[SpacingSize + 2:CellSize * len(Page):DotSpacing, DotCentering] = 1
		# Create markers
		#Grid = {
		#	4: (0, 0),
		#	5: (CellSize * ColNum, 0),
		#	6: (0, CellSize * len(Page))
		#	}
		#for Index, Item in Grid.items(): 
		#	Matrix[Item[1]:Item[1] + SpacingSize, Item[0]:Item[0] + SpacingSize] = KittyPawprint(Index, ArUcoDict, SpacingSize)
		# Append page
		Result.append(Matrix)
	# Return
	SD = '\n'.join(SignableData)
	gpg = gnupg.GPG()
	Signed = gpg.sign(SD, detach=True, clearsign=False, binary=True)
	print(Signed)
	return Result

def CreatePDF(SvgPages, OutputFileName, JobName, RunID, PdfLeftMargin, PdfTopMargin, PdfLineSpacing, PdfFontFamily, PdfFontSize, PdfPageHeight, TqdmAscii): # pragma: no cover
	CanvasPDF = canvas.Canvas(OutputFileName)
	Timestamp = str(datetime.datetime.now().replace(microsecond = 0))
	for PageNumber, Page in tqdm.tqdm(
		enumerate(SvgPages),
		total = len(SvgPages),
		desc = f'Convert pages to PDF',
		ascii = TqdmAscii
	):
		# Set font
		CanvasPDF.setFont(PdfFontFamily, PdfFontSize)
		# Convert SVG page
		ObjectPage = svg2rlg(io.StringIO(Page))
		# Captions
		CanvasPDF.drawString(PdfLeftMargin * mm, (PdfPageHeight - PdfTopMargin - (PdfLineSpacing * 1)) * mm, f'Name: {JobName}')
		CanvasPDF.drawString(PdfLeftMargin * mm, (PdfPageHeight - PdfTopMargin - (PdfLineSpacing * 2)) * mm, f'{Timestamp}, run ID: {RunID}, page {PageNumber + 1} of {len(SvgPages)}')
		CanvasPDF.drawString(PdfLeftMargin * mm, (PdfPageHeight - PdfTopMargin - (PdfLineSpacing * 3)) * mm, f'manuscrypt 0.9.0. Available at: hui.ru')
		# Draw pawprints
		renderPDF.draw(ObjectPage, CanvasPDF, 0, 0)
		# Newpage
		CanvasPDF.showPage()
	# Save pdf
	CanvasPDF.save()

k = CreatePixelSheets('BUT I MUST EXPLAIN TO YOU HOW ALL THIS  MISTAKEN IDEA OF DENOUNCING PLEASURE ANDPRAISING PAIN WAS BORN AND I WILL GIVE  YOU A COMPLETE ACCOUNT OF THE SYSTEM,   AND EXPOUND THE ACTUAL TEACHINGS OF THE GREAT EXPLORER OF THE TRUTH, THE MASTER-BUILDER OF HUMAN HAPPINESS. NO ONE RE-  JECTS, DISLIKES, OR AVOIDS PLEASURE IT- SELF, BECAUSE IT IS PLEASURE, BUT BECAU-SE THOSE WHO DO NOT KNOW HOW TO PURSUE  PLEASURE RATIONALLY ENCOUNTER CONSEQUEN-CES THAT ARE EXTREMELY PAINFUL. NOR AGA-IN IS THERE ANYONE WHO LOVES OR PURSUES OR DESIRES TO OBTAIN PAIN OF ITSELF, BE-CAUSE IT IS PAIN, BUT BECAUSE OCCASIO-  NALLY CIRCUMSTANCES OCCUR IN WHICH TOIL AND PAIN CAN PROCURE HIM SOME GREAT PLE-ASURE. TO TAKE A TRIVIAL EXAMPLE, WHICH OF US EVER UNDERTAKES LABORIOUS PHYSICALEXERCISE, EXCEPT TO OBTAIN SOME ADVANTA-GE FROM IT? BUT WHO HAS ANY RIGHT TO    FIND FAULT WITH A MAN WHO CHOOSES TO EN-JOY A PLEASURE THAT HAS NO ANNOYING CON-SEQUENCES, OR ONE WHO AVOIDS A PAIN THATPRODUCES NO RESULTANT PLEASURE?', 20, 8, 2, 3, 2, 3, 34, 1, 5, '.#')
#m = MakeQR(['I AM NOT A MAN O', 'SHOULD KNOW WHAT', 'OF MY WARRIORS r', 'MNOPQRSTUWX1212Z', 'YZ0126666456789J', 'AZ AZAZ AZ AZAZ '], 27, 0, 'L', 'AERT', 'A000')
#m1 = MakeQR(['F MANY WORDS YOU', 'THAT MEANS 1234 ', 'ARE ON THEIR WAY', 'MNOPQRSTUWX1212Z', 'YZ0126666456789J', 'AZ AZAZ AZ AZAZ '], 27, 0, 'L', 'AERT', 'A000', True)
#k = numpy.zeros((m.shape[0], m.shape[0] * 2 + 5))
#k[0:m.shape[0], 0:m.shape[0]] = m
#k[0:m.shape[0], (m.shape[0] + 5):(m.shape[0]*2 + 5)] = m1
Svgs = DrawSvg(k, 210, 297, 28, 28, 40, '.#')
CreatePDF(Svgs, "test.pdf", "Teft", "345345", 28, 20, 5, 'Courier-Bold', 10, 297, '.#')
#m = MonogramTest(MonogramLoad())
#PrintMatrix(m)
