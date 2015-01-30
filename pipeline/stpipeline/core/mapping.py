#!/usr/bin/env python
""" This module contains wrappers to make systems calls for different aligners
most of the options can be passed as arguments
"""

import logging 
import subprocess
from stpipeline.common.utils import *
from stpipeline.common.fastq_utils import *
import pysam
    
def bowtie2Map(fw, rv, ref_map, trim=42, cores=8, 
               qual64=False, discordant=False, outputFolder=None, keep_discarded_files=False):  
    """
    maps pair end reads against a given genome using bowtie2 
    """
    
    logger = logging.getLogger("STPipeline")
    
    if (fw.endswith(".fastq") or fw.endswith(".fq")) and (rv.endswith(".fastq") or rv.endswith(".fq")):
        outputFile = replaceExtension(getCleanFileName(fw),"_mapped.sam")
        if outputFolder is not None and os.path.isdir(outputFolder): 
            outputFile = os.path.join(outputFolder, outputFile)
        
        outputFileDiscarded = replaceExtension(getCleanFileName(fw),"_mapped_discarded.fastq")
        if outputFolder is not None and os.path.isdir(outputFolder): 
            outputFileDiscarded = os.path.join(outputFolder, outputFileDiscarded)    
    else:
        errror = "Error: Input format not recognized " + fw + " , " + rv
        logger.error(errror)
        raise RuntimeError(errror + "\n")
    
    logger.info("Start Bowtie2 Mapping")
    
    qual_flags = ["--phred64"] if qual64 else ["--phred33"] 
    core_flags = ["-p", str(cores)] if cores > 1 else []
    trim_flags = ["--trim5", trim] 
    io_flags   = ["-q", "-X", 2000, "--sensitive"] ##500 (default) is too selective
    io_flags  += ["--no-discordant"] if discordant else []

    args = ['bowtie2']
    args += trim_flags
    args += qual_flags
    args += core_flags
    args += io_flags
    args += ["-x", ref_map, "-1", fw, "-2", rv, "-S", outputFile] 
    if keep_discarded_files:
        args += ["--un", outputFileDiscarded]
  
    proc = subprocess.Popen([str(i) for i in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, errmsg) = proc.communicate()

    if not fileOk(outputFile):
        error = "Error: output file is not present : " + outputFile
        logger.error(error)
        logger.error(stdout)
        logger.error(errmsg)
        raise RuntimeError(error + "\n")
    else:
        procOut = [x for x in errmsg.split("\n") if x.find("Warning") == -1 and x.find("Error") == -1]
        logger.info('Mapping stats on paired end mode with 5-end trimming of ' + str(trim))
        for line in procOut:
            logger.info(str(line))

    logger.info("Finish Bowtie2 Mapping")

    return outputFile


def bowtie2_contamination_map(fastq, contaminant_index, trim=42, cores=8, 
                              qual64=False, outputFolder=None):
    """ 
    Maps reads against contaminant genome index with Bowtie2 and returns
    the fastq of unaligned reads.
    """
    
    logger = logging.getLogger("STPipeline")

    if fastq.endswith(".fastq") or fastq.endswith(".fq"):
        contaminated_file = replaceExtension(getCleanFileName(fastq),"_contaminated.sam")
        if outputFolder is not None and os.path.isdir(outputFolder): 
            contaminated_file = os.path.join(outputFolder, contaminated_file)
            
        clean_fastq = replaceExtension(getCleanFileName(fastq),"_clean.fastq")
        if outputFolder is not None and os.path.isdir(outputFolder): 
            clean_fastq = os.path.join(outputFolder, clean_fastq)
    else:
        error = "Error: Input format not recognized " + fastq
        logger.error(error)
        raise RuntimeError(error + "\n")

    logger.info("Start Bowtie2 Mapping rRNA")
    
    qual_flags = ["--phred64"] if qual64 else ["--phred33"]
    core_flags = ["-p", str(cores)] if cores > 1 else []
    trim_flags = ["--trim5", trim]
    io_flags   = ["-q","--sensitive"]
    
    args = ['bowtie2']
    args += trim_flags
    args += qual_flags
    args += core_flags
    args += io_flags
    args += ["-x", contaminant_index, "-U", fastq, "-S", contaminated_file, "--un", clean_fastq]

    proc = subprocess.Popen([str(i) for i in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, errmsg) = proc.communicate()

    if not fileOk(contaminated_file) or not fileOk(clean_fastq):
        error = "Error: output file is not present " + contaminated_file + " , " + clean_fastq
        logger.error(error)
        logger.error(stdout)
        logger.error(errmsg)
        raise RuntimeError(error + "\n")
    else:
        procOut = [x for x in errmsg.split("\n") if x.find("Warning") == -1 and x.find("Error") == -1]
        logger.info('Contaminant mapping stats against ' +
                       contaminant_index + ' with 5-end trimming of ' +
                       str(trim))
        for line in procOut:
            logger.info(str(line))

    logger.info("Finish Bowtie2 Mapping rRNA")

    return clean_fastq, contaminated_file

def filterUnmapped(sam, discard_fw=False, discard_rw=False, outputFolder=None, keep_discarded_files=False):
    """ 
    Filter unmapped and discordant reads
    """
    
    #TODO could optimize that by telling bowtie2 to not report unmapped reads
    
    logger = logging.getLogger("STPipeline")

    if sam.endswith(".sam"):
        outputFileSam = replaceExtension(getCleanFileName(sam),'_filtered.sam')
        if outputFolder is not None and os.path.isdir(outputFolder): 
            outputFileSam = os.path.join(outputFolder, outputFileSam)
            
        outputFileSamDiscarded = replaceExtension(getCleanFileName(sam),'_filtered_discarded.sam')
        if outputFolder is not None and os.path.isdir(outputFolder): 
            outputFileSamDiscarded = os.path.join(outputFolder, outputFileSamDiscarded)
    else:
        error = "Error: Input format not recognized " + sam
        logger.error(error)
        raise RuntimeError(error + "\n")

    logger.info("Start converting SAM to BAM and filtering unmapped")
    
    # Remove found duplicates in the Forward Reads File
    input = pysam.Samfile(sam, "r")
    output = pysam.Samfile(outputFileSam, 'wh', header=input.header)
    if keep_discarded_files:
        outputDiscarded = pysam.Samfile(outputFileSamDiscarded, 'wh', header=input.header)
        
    dropped = 0
    for read in input:
        # filtering out not pair end reads
        if not read.is_paired:
            error = "Error: input Sam file contains not paired reads"
            logger.error(error)
            raise RuntimeError(error + "\n")

        if read.is_proper_pair and not read.mate_is_unmapped:
            # if read is a concordant pair and it is mapped,
            output.write(read)
        elif not read.is_proper_pair and not read.is_unmapped:
            # if read is a discordant mapped pair or uniquely mapped (mixed mode bowtie2)
            if read.is_read1 and not discard_fw:
                # if read is forward and we dont want to discard it
                output.write(read)
            elif read.is_read2 and not discard_rw:
                # if read is reverse and we dont want to discard it
                output.write(read)
            else:
                # I want to discard both forward and reverse and unmapped
                dropped += 1
                if keep_discarded_files:
                    outputDiscarded.write(read)
                pass
        else:
            # not mapped stuff discard
            dropped += 1
            if keep_discarded_files:
                outputDiscarded.write(read)
            pass  
            
    input.close()
    output.close()

    if not fileOk(outputFileSam):
        error = "Error: output file is not present " + outputFileSam
        logger.error(error)
        raise RuntimeError(error + "\n")
    
    logger.info("End converting SAM to BAM and filtering unmapped, dropped reads = " + str(dropped))
    
    return outputFileSam


def getTrToIdMap(readsContainingTr, idFile, m, k, s, l, e, oh, outputFolder=None, keep_discarded_files=False):
    """ 
    Barcode demultiplexing mapping with taggd
    """
    
    logger = logging.getLogger("STPipeline")
    
    if not fileOk(readsContainingTr) or not fileOk(idFile):
        error = "Error: Input files not present, transcript file = " 
        + readsContainingTr + " ids = " + idFile
        logger.error(error)
        raise RuntimeError(error + "\n")
    
    logger.info("Start Mapping against the barcodes")
    
    outputFilePrefix = replaceExtension(getCleanFileName(readsContainingTr),'_demultiplexed')
    if outputFolder is not None and os.path.isdir(outputFolder): 
        outputFilePrefix = os.path.join(outputFolder, outputFilePrefix)

    # Check format.
    suffix = getExtension(readsContainingTr).lower()
    if suffix == "fastq": suffix = "fq"
    if not (suffix == "fq" or suffix == "sam" or suffix == "bam"):
        raise ValueError("Expected FASTQ, SAM or BAM file.")

    outputFile = outputFilePrefix + ".matched." + suffix

    # taggd options
    args = ['taggd_demultiplex.py',
            "--max_edit_distance", str(m),
            "--k", str(k),
            "--start_position", str(s),
            "--overhang", str(oh)]
    if not keep_discarded_files:
        args.append("--only_output_matched")
    args += [idFile, readsContainingTr, outputFilePrefix]

    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, errmsg) = proc.communicate()
 
    if not fileOk(outputFile):
        error = "Error: output file is not present " + outputFile
        logger.error(error)
        logger.error(stdout)
        logger.error(errmsg)
        raise Exception(error + "\n")
    else:
        procOut = stdout.split("\n")
        logger.info('Barcode Mapping stats :')
        for line in procOut: 
            logger.info(str(line))

    logger.info("Finish Mapping against the barcodes")
    
    return outputFile