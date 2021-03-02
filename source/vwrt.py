#!/usr/bin/python

# Include standard modules
import pathlib
import re
import numpy as np
import getopt, sys
import errno
import os

def flattenonedeep(intup):
	#using simple solution for one-deep nesting #https://stackoverflow.com/a/11264751
	#if flattening of unknown nesting structure is needed use #https://stackoverflow.com/a/5828872
	return [val for sub in intup for val in sub]

def appendtostem(inpath, toappend):
	ipth=pathlib.Path(inpath)
	if ipth == pathlib.Path(f'{ipth.stem}{ipth.suffix}'):
		return pathlib.Path(f'{ipth.stem}{toappend}{ipth.suffix}')
	return ipth.parent / f'{ipth.stem}{toappend}{ipth.suffix}'

def findopenpath(inpath):
	ipth=pathlib.Path(inpath)
	tempth=ipth
	tempnum=0
	while tempth.exists():
		tempnum+=1
		tempth=appendtostem(ipth, f' ({tempnum})')
	return tempth

def genvolpath(inpath, volumecutoff='-30dB', duration=0.5):
	return appendtostem(inpath, f'_vco={volumecutoff}_d={duration}vol').with_suffix('.txt')

def readsilencetimes(inpath): #extracts silence times from vol.txt file
	voltext=inpath.read_text()
	myrestarts = r'(?:silence_start: ([\d,\.]+))'
	myreends = r'(?:silence_end: ([\d,\.]+))'
	return [re.findall(myrestarts, voltext), re.findall(myreends, voltext)]

def cleansilencetimes(intimelist):
	tmp=np.asarray(flattenonedeep(intimelist))
	unq=np.unique(tmp, return_counts=True)
	print(f'unq:{unq}')
	clntms=list(np.sort(np.asarray([t for ind, t in enumerate(unq[0]) if unq[1][ind]==1], dtype=np.float64)))
	#print(f'clntms:\n{clntms}')
	return clntms

def getcleansilence(inpath):
	return cleansilencetimes(readsilencetimes(inpath))

def callterm(tocall):
	os.system(tocall)
	print('Command completed')
	
def genmeat(inst, speed1=1, speed2=2, video=True, audio=True):
	print('genmeat:')
	print(f'\tinst={inst}, \n\tspeed1={speed1}, \n\tspeed2={speed2}, \n\tvideo={video}, \n\taudio={audio}')
	#initial clip
	vidmeat=[f'[0:v]trim=0:{inst[0]},setpts={1/speed1}*(PTS-STARTPTS)[v0]; '] if video else []
	audmeat=[f'[0:a]atrim=0:{inst[0]},asetpts=PTS-STARTPTS,atempo={speed1}[a0]; '] if audio else []
	#intermediate clips
	i=0
	for i in range(len(inst)-1):
		myspeed = speed1 if i%2==1 else speed2
		print(f'i={i}, myspeed={myspeed}')
		if video:
			print(f'''vidmeat.append(f'[0:v]trim={inst[0+i]}:{inst[1+i]},setpts={1/myspeed}*(PTS-STARTPTS)[v{i+1}]; ')''')
			vidmeat.append(f'[0:v]trim={inst[0+i]}:{inst[1+i]},setpts={1/myspeed}*(PTS-STARTPTS)[v{i+1}]; ')
		if audio:
			audmeat.append(f'[0:a]atrim={inst[0+i]}:{inst[1+i]},asetpts=PTS-STARTPTS,atempo={myspeed}[a{i+1}]; ')
	#last clip
	i+=1
	myspeed = speed1 if i%2==1 else speed2
	if video:
		vidmeat.append(f'[0:v]trim={inst[0+i]},setpts={1/myspeed}*(PTS-STARTPTS)[v{i+1}]; ')
	if audio:
		audmeat.append(f'[0:a]atrim={inst[0+i]},asetpts=PTS-STARTPTS,atempo={myspeed}[a{i+1}]; ')
		
	#
	cnc=[f'''{f'[v{j}]' if video else ''}{f'[a{j}]' if audio else ''}''' for j in range(i+2)] + [f'concat=n={i+2}:v={int(video)}:a={int(audio)}']
	return (vidmeat, audmeat, cnc)

def geneditcommand(inpath, outpath, inst, speed1=1, speed2=2, video=True, audio=True, onlyfiltercomplex=False, invac=None, profilebaseline=False):
	print('geneditcommand')
	#takes inpath, outpath, in start time list, video bool, audio bool
	np.array(inst, dtype=np.float64)
	assert video or audio #at least one of video and audio must be true
	vac=genmeat(inst, speed1=speed1, speed2=speed2, video=video, audio=audio) if invac is None else invac
	mycmd=f'''ffmpeg -loglevel verbose -i "{inpath}" -filter_complex "{''.join([''.join(m) for m in vac])}" -preset superfast {"-profile:v baseline " if profilebaseline else ""}"{outpath}"'''
	if onlyfiltercomplex:
		mycmd=[f'''ffmpeg -loglevel verbose -i "{inpath}" -filter_complex_script "''', ''.join([''.join(m) for m in vac]), f'''" -preset superfast {"-profile:v baseline " if profilebaseline else ""}"{outpath}"''']
	return mycmd

def vwrtstart(inpath, outpath=None, speed1=1, speed2=2, volumecutoff='-30dB', duration=0.5, overwritevid=False, overwritevol=True, video=True, audio=True, splitclips=False):
	print('vwrtstart')
	#assert pathlib.Path(inpath).exists()
	op=findopenpath(appendtostem(inpath,'_out') if outpath is None else outpath)
	vp=genvolpath(inpath, volumecutoff=volumecutoff, duration=duration)
	print(vp)
	if not overwritevid:
		op=findopenpath(op)
	if not overwritevol:
		vp=findopenpath(vp)
	#Generate Vol File
	if not vp.exists():
		volcall = f'ffmpeg -i "{inpath}" -af silencedetect=noise={volumecutoff}:d={duration} -f null - 2> "{vp}"'
		print(volcall)
		callterm(volcall)
		if not vp.exists():
			print('Cannot find vp. Is the input path correct?')
	global myst
	myst=getcleansilence(vp)
	fp=pathlib.Path(appendtostem(op, '_command')).with_suffix('.txt')
	if not splitclips:
		mycmd=geneditcommand(inpath, op, myst, speed1=speed1, speed2=speed2, video=video, audio=audio)
		#print(mycmd)
		mycmdcomplex=geneditcommand(inpath, op, myst, speed1=speed1, speed2=speed2, video=video, audio=audio, onlyfiltercomplex=True)
		print(len(mycmdcomplex[1]))
		with open(fp, "w") as text_file:
			print(mycmdcomplex[1], file=text_file)
		print(mycmdcomplex[0] + str(fp) + mycmdcomplex[2])
		return mycmdcomplex[0] + str(fp) + mycmdcomplex[2]
	else:
		global cliplist
		cliplist=gencliplist(myst, speed1=speed1, speed2=speed2)
		global bnc
		bnc=getbtntcumu(cliplist, vp=vp)
		#print(f'bnc={bnc}')
		#print(f'cliplist=\n\t{cliplist}')
		lcl=len(cliplist)
		n=0
		step=10
		inds=[]
		for n in range(1, int(lcl/(step))):
			inds.append([x for x in range((n-1)*step, n*step+1)])
		inds.append([x for x in range(n*step, lcl)])
		print(f'inds=\n\t{inds}')
		
		prev=0
		for i, indl in enumerate(inds):
			seektime=float(cliplist[indl[0]][0])
			cliplen=bnc[2][indl[-1]]-bnc[2][indl[0]]
			prev=indl[-1]
			print(f'tobetterunderstand=\n\t{[(subcumu, bnc[0][subcumu], bnc[1][subcumu], s2hmst(bnc[2][subcumu]), cliplist[subcumu], s2hmst(cliplist[subcumu][0])) for subcumu in range(indl[0]-1,indl[-1]+2)]}')
			#print(f'{bnc[2][indl[-1]]}-{bnc[2][indl[0]]}')
			print(f'cliplen={cliplen}')
			
			myfp=pathlib.Path(appendtostem(fp, f'{i:03}'))
			myop=pathlib.Path(appendtostem(op, f'{i:03}'))
			myvac=genselectmeat(cliplist, indl, video=video, audio=audio)
			mycmdcomplex=geneditcommand(inpath, myop, myst, speed1=speed1, speed2=speed2, video=video, audio=audio, onlyfiltercomplex=True, invac=myvac)
			#print(len(mycmdcomplex[1]))
			with open(myfp, "w") as text_file:
				print(mycmdcomplex[1], file=text_file)
			print(mycmdcomplex[0][:24] + ' -ss ' + str(seektime) + mycmdcomplex[0][24:] + str(myfp) + mycmdcomplex[2][:19] + ' -t ' + str(cliplen) + mycmdcomplex[2][19:])
			print("\n\n")
			
def makesplit(inpath, outpath, segment='00:05:00'):
	tocom=f'ffmpeg -i "{inpath}" -c copy -map 0 -segment_time {segment} -f segment -reset_timestamps 1 "{pathlib.Path(outpath).with_suffix("")}%03d{pathlib.Path(outpath).suffix}"'
	print(tocom)
	os.system(tocom)
	return tocom

def overlayframes(inpath, outpath, x='(w-tw)/2'):
	tocom = f'''ffmpeg -i "{inpath}" -vf "drawtext=fontfile=Arial.ttf: text='%{{frame_num}}': start_number=1: x={x}: y=h-(2*lh): fontcolor=black: fontsize=20: box=1: boxcolor=white: boxborderw=5, drawtext=fontfile=Arial.ttf: timecode='00\:00\:00\:00': r=25: x={x}: y=h-(4*lh): fontcolor=white: fontsize=20: box=1: boxcolor=0x00000099: boxborderw=5" -c:a copy "{outpath}"'''
	print(tocom)
	os.system(tocom)
	#return tocom
	
def concatsplitfiles(insplitfiles, outpath):
	mytext=[f"file '{x}'" for x in insplitfiles]
	mytextpath=outpath.parent/'mylist.txt'
	if mytextpath.exists():
		os.remove(mytextpath)
	with open(mytextpath, "w") as text_file:
		print('\n'.join(mytext), file=text_file)
	tocom = f'ffmpeg -f concat -safe 0 -i "{mytextpath}" -c copy "{outpath}"'
	print(tocom)
	os.system(tocom)
	
def runonvid(inpath, folderpath='/Users/evn/Downloads/shortvids', addFrames=True, speed1=None, speed2=None):
	s1, s2 = 1.5 if speed1 is None else speed1, 4.0 if speed2 is None else speed2
	global allsplitoutputs
	wordir=pathlib.Path(folderpath)/(str(pathlib.Path(inpath).name)+' folder')
	wordir.mkdir(parents=True, exist_ok=True)
	outpath=wordir/(str(pathlib.Path(inpath).with_suffix("").name)+'_shortened'+pathlib.Path(inpath).suffix)
	if outpath.exists():
		print(f'{outpath} already exists. ending')
		return
	framedfile=pathlib.Path(folderpath)/(str(pathlib.Path(inpath).with_suffix("").name)+'_framed'+pathlib.Path(inpath).suffix)
	if addFrames:
		if not framedfile.exists():
			print(f'generating {framedfile}')
			overlayframes(inpath, framedfile)
		else:
			print(f'{framedfile} already exists. skipping')
	else:
		framedfile=pathlib.Path(inpath)
	splitfiles=wordir/pathlib.Path(inpath).name
	makesplit(framedfile, splitfiles)
	i = 0
	tempsplitpath=pathlib.Path(f'{splitfiles.with_suffix("")}{i:03}{pathlib.Path(outpath).suffix}')
	allsplitclips=[]
	while tempsplitpath.exists():
		allsplitclips.append(tempsplitpath)
		i+=1
		tempsplitpath=pathlib.Path(f'{splitfiles.with_suffix("")}{i:03}{pathlib.Path(outpath).suffix}')
	allsplitoutputs=[pathlib.Path(str(x.with_suffix(""))[:-3] + '_out_' + str(x.with_suffix(""))[-3:] + x.suffix) for x in allsplitclips]
	allcommands=[vwrtstart(x, outpath=allsplitoutputs[xi], speed1=s1, speed2=s2, splitclips=False) for xi, x in enumerate(allsplitclips)] 
	for xi, x in enumerate(allsplitoutputs):
		if not x.exists():
			print(f'creating {xi}/{len(allsplitoutputs)} {x}')
			os.system(allcommands[xi])
		else:
			print(f'{x} already exists. skipping')
	print(f'concatenating to {outpath}')
	concatsplitfiles(allsplitoutputs, outpath)
		
		

if __name__ == '__main__':
	# Get full command-line arguments
	full_cmd_arguments = sys.argv
	
	# Keep all but the first
	argument_list = full_cmd_arguments[1:]
	
	#print(argument_list)
	
	short_options = "hi:t:s:o:vfd"
	long_options = ["help", "input=", "talk-speed=", "silence-speed=", "outdir=", "verbose", "add-frames", "dry-run"]
	
	try:
		arguments, values = getopt.getopt(argument_list, short_options, long_options)
	except getopt.error as err:
		# Output error, and return with an error code
		print (str(err))
		sys.exit(2)
		
	invidlist=[]
	t_list=[]
	s_list=[]
	folderpathlist=[]
	booladdframes=False
	booldryrun=False
	# Evaluate given options
	for current_argument, current_value in arguments:
		#print(f"{current_argument}, {current_value}")
		if current_argument in ("-v", "--verbose"):
			print ("Enabling verbose mode")
		elif current_argument in ("-h", "--help"):
			helpmessage="\n".join([
			"usage: vwrt.py [-i INPUT] [-t SPEED] [-s SPEED] [-o OUTDIR]",
			"",
			"required arguments:",
			"  -i INPUT, --input INPUT",
			"                        add input video",
			"  -t SPEED, --talk-speed SPEED",
			"                        set talk speed",
			"  -s SPEED, --silence-speed SPEED",
			"                        set silence speed",
			"  -o OUTDIR, --outdir OUTDIR",
			"                        set output directory",
			"",
			"optional arguments:",
			"  -h, --help            show this help message and exit",
			"  -v, --verbose         set verbose mode",
			"  -f, --add-frames      overlay timecode on video before processing",
			"  -d, --dry-run         skip video processing"
			])
			print (helpmessage)
			sys.exit(0)
		elif current_argument in ("-f", "--add-frames"):
			booladdframes=True
		elif current_argument in ("-t", "--talk-speed"):
			if 0.01<float(current_value)<100:
				t_list.append(current_value)
			else:
				raise ValueError("value must be between 0.01 and 100.0", current_value)
		elif current_argument in ("-s", "--silence-speed"):
			if 0.01<float(current_value)<100:
				s_list.append(current_value)
			else:
				raise ValueError("value must be between 0.01 and 100.0", current_value)
		elif current_argument in ("-d", "--dry-run"):
			booldryrun=True
		elif current_argument in ("-i", "--in"):
			if pathlib.Path(current_value).is_file():
				invidlist.append(current_value)
			else:
				raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), current_value)
		elif current_argument in ("-o", "--outdir"):
			if pathlib.Path(current_value).is_dir():
				folderpathlist.append(current_value)
			elif pathlib.Path(current_value).exists():
				raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), current_value)
			else:
				raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), current_value)
	if not (invidlist and folderpathlist):
		raise TypeError("at least one input file and output folder are required")
	if not (t_list and s_list):
		raise TypeError("at least one talk-speed and silence-speed are required")
	for count, invid in enumerate(invidlist):
		folderpath=folderpathlist[count%len(folderpathlist)]
		#booladdframes=booladdframes
		s1=t_list[count%len(t_list)]
		s2=s_list[count%len(s_list)]
		print(f"{invid}, {folderpath}, {booladdframes}, {s1}, {s2}")
		if not booldryrun:
			runonvid(invid, folderpath=folderpath, addFrames=booladdframes, speed1=float(s1), speed2=float(s2))
			#print('done')
	#if booldryrun:
	#	return
			