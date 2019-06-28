#!/usr/bin/env Rscript
args = commandArgs(trailingOnly=TRUE)

suppressWarnings(library(phyloseq))

biom.fn <- args[1]
tree.fn <- args[2]
out.fn <- args[3]
DB = args[4]

parse.qiime2.silva <- function(char.vec){
    char.vec = gsub("^[[:space:]]{1,}", "", char.vec)
    char.vec = gsub("[[:space:]]{1,}$", "", char.vec)
    if (length(char.vec) > 0) {
        tax.names <- c("Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species")[1:length(char.vec)]
        names(char.vec) <- tax.names
    }
    Tranks = c(D_0= "Kingdom", D_1= "Phylum", D_2 = "Class", D_3 = "Order", D_4 = "Family", D_5 = "Genus", D_6 = "Species")
    ti = grep("D\\_[[:alnum:]]+\\_\\_", char.vec)
    if (length(ti) == 0L) {
        if (char.vec == "Unassigned"){
            taxvec <- rep(NA, 7)
            names(taxvec) <- c("Kingdom", "Phylum", "Class", "Order", "Family", "Genus", "Species")
        } else{
            cat("hmmmm\n", char.vec, "\n")
            taxvec = char.vec
        }
    }
    else {
        taxvec = gsub("D\\_[[:alnum:]]+\\_\\_", "", char.vec)
        repranks = Tranks[substr(char.vec[ti], 1, 3)]
        #cat(repranks, "\n")
        #cat(taxvec, "\n\n")
        names(taxvec)[ti[!is.na(repranks)]] = repranks[!is.na(repranks)]
    }
    return(taxvec)
}

if (DB == "SILVA" | DB == "silva"){
    parseFunction <- parse.qiime2.silva
    cat("using SILVA parser ...")
} else if (DB == "GG" | DB == "gg" | DB == "greengenes"){
    parseFunction <- parse_taxonomy_greengenes
} else{
    parseFunction=parse_taxonomy_default
}


OTU <- import_biom(biom.fn, parseFunction=parseFunction, treefilename=tree.fn)
TAX <- tax_table(OTU)
if (dim(TAX)[2] > 7){
    # lets not use the NA col of parse_taxonomy_greengenes (All NA is `Unassigned`)
    TAX <- TAX[,1:7]
    tax_table(OTU) <- TAX
}


saveRDS(OTU, out.fn)
