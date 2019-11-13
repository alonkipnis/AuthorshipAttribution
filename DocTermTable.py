import numpy as np
import scipy
from scipy.sparse import vstack

from HC_aux import hc_vals, two_counts_pvals, two_sample_test

from utils import *

def change_dtm_dictionary(dtm, old_vocab, new_vocab):
    """
       Switch columns in doc-term matrix according to new_vocab 
       Words not in new_vocab are ignored
       dtm is a document-term matrix (sparse format)
       old_vocab and new_vocab are lists of words (without duplicaties)
    """

    new_dtm = scipy.sparse.lil_matrix(np.zeros((dtm.shape[0],
                                             len(new_vocab))))
    for i, w in enumerate(new_vocab):
        try:
            new_dtm[:, i] = dtm[:, old_vocab.index(w)]
        except:
            None
    return new_dtm


class DocTermTable(object):
    """ Interface for p-value, Higher Criticism (HC), and cosine
    similarity computations with with respect to a document-term matrix.
 
    Args: 
            dtm -- (sparse) doc-term matrix.
            feature_names -- list of names for each column of dtm.
            document_names -- list of names for each row of dtm.
            stbl -- type of HC statistic to use 

    To Do:
        - DONE: implement a method to collapse the table to a single row
          in order to save memory and computing time
        - rank of ChiSquare in LOO
        - log(pval) in ChiSquare test 

    """
    def __init__(self, dtm, feature_names=[], document_names=[], stbl=True):
        """ 
        Args: 
            dtm -- (sparse) doc-term matrix.
            feature_names -- list of names for each column of dtm.
            document_names -- list of names for each row of dtm.
            stbl -- type of HC statistic to use 
        """

        if document_names == []:
            document_names = ["doc" + str(i) for i in range(dtm.shape[0])]
        self._doc_names = dict([
            (s, i) for i, s, in enumerate(document_names[:dtm.shape[0]])
        ])
        self._feature_names = feature_names  #: list of feature names (vocabulary)
        self._dtm = dtm  #: doc-term-table (matrix)
        self._stbl = stbl  #: type of HC score to use

        if dtm.sum() == 0:
            raise ValueError(
                "seems like all counts are zero. "\
                +"Did you pass the wrong data format?"
            )

        self.__compute_internal_stat()

    def __compute_internal_stat(self):
        """summarize internal doc-term-table"""

        self._terms_per_doc = np.squeeze(np.array(
            self._dtm.sum(1))).astype(int)
        self._counts = np.squeeze(np.array(self._dtm.sum(0))).astype(int)

        #keep HC score of each row w.r.t. the rest
        #pv_list = self.__per_doc_Pvals()
        self._internal_scores = []
        for row in self._dtm:
            cnt = np.squeeze(np.array(row.sum(0)).astype(int))
            pv = self._get_Pvals(cnt, within = True)
            hc, p_thr = hc_vals(pv, stbl=self._stbl, alpha=0.45)
            self._internal_scores += [hc]

    def __per_doc_Pvals(self):
        """Pvals of each row in dtm with respect to the rest"""

        pv_list = []

        #pvals when removing one row at a time
        counts = self._counts
        if self._dtm.shape[0] == 1:  # internal score is undefined
            return []
        for r in self._dtm:
            c = np.squeeze(np.array(r.todense()))
            pv = two_counts_pvals(c, counts - c).pval
            pv_list += [pv.values]

        return pv_list

    def get_feature_names(self):
        return self._feature_names

    def get_document_names(self):
        return self._doc_names

    def get_counts(self):
        return self._counts

    def _get_Pvals(self, counts, within=False):
        """ Returns pvals from a list counts 

        Args:
            counts -- 1D array of feature counts.
            within -- indicates weather to subtracrt counts of dtm
                      from internal counts (this option is useful 
                        whenever we wish to compute Pvals of a 
                        document wrt to the rest)
        Returns:
            list of P-values
        """
        cnt0 = np.squeeze(np.array(self._counts))
        cnt1 = np.squeeze(np.array(counts))

        assert (cnt0.shape == cnt1.shape)

        if within:
            cnt2 = cnt0 - cnt1
            if np.any(cnt2 < 0):
                raise ValueError("'within == True' is invalid")
            pv = two_counts_pvals(cnt1, cnt2).pval
        else:
            pv = two_counts_pvals(cnt1, cnt0).pval
        return pv.values 

    def _get_counts(self, dtbl, within=False) :
        """ Returns two list of counts, one from an 
        external table and one from 'self' while considering
         'within' parameter to reduce counts from 'self'.

        Args: 
            dtbl -- DocTermTable representing another frequency 
                    counts table
            within -- indicates whether counts of dtbl should be 
                    reduced from from counts of self._dtm

        Returns:
            cnt0 -- adjusted counts of self
            cnt1 -- adjusted counts of dtbl
        """

        if list(dtbl._feature_names) != list(self._feature_names):
            print(
            "Features of 'dtbl' do not match current DocTermTable\
             intance. Changing dtbl accordingly."
            )
            #Warning for changing the test object
            dtbl.change_vocabulary(self._feature_names)
            print("Completed.")

        cnt0 = self._counts
        cnt1 = dtbl._counts
        if within:
            cnt0 = cnt0 - cnt1
            if np.any(cnt0 < 0):
                raise ValueError("'within == True' is invalid")
        return cnt0, cnt1

    def get_Pvals(self, dtbl):
        """ return a list of p-values of another DocTermTable with 
        respect to 'self' doc-term table.

        Args: 
            dtbl -- DocTermTable object with respect to which to
                    compute pvals
        """

        if dtbl._feature_names != self._feature_names:
            print(
                "Warning: features of 'dtbl' do not match object",
                " Changing dtbl accordingly. "
            )
            #Warning for changing the test object
            dtbl.change_vocabulary(self._feature_names)
            print("Completed.")

        return self._get_Pvals(dtbl.get_counts())

    def two_table_test(self, dtbl, within=False, stbl=None) :
        """counts, p-values, and HC with 
        respect to another DocTermTable
        """
        if stbl == None :
            stbl = self._stbl

        cnt0, cnt1 = self._get_counts(dtbl, within=within)
        df = two_sample_test(cnt0, cnt1, stbl=stbl)
        df.loc[:,'feat'] = self._feature_names
        return df


    def per_doc_Pvals_LOO(self, dtbl):
        """ return a list of internal pvals after adding another 
        table to the current one.

        Args:
            dtbl -- DocTermTable to add and to compute score with
                    respect to it
        """

        if dtbl._feature_names != self._feature_names:
            print(
                "Warning: features of 'dtbl' do not match object. "\
                +"Changing dtbl accordingly... "
            )
            #Warning for changing the test object
            dtbl.change_vocabulary(self._feature_names)

        return self.__per_doc_Pvals_LOO(dtbl._dtm)

    def change_vocabulary(self, new_vocabulary):
        """ Shift and remove columns of self._dtm so that it 
        represents counts with respect to new_vocabulary
        """
        new_dtm = scipy.sparse.lil_matrix(
            np.zeros((self._dtm.shape[0], len(new_vocabulary))))
        old_vocab = self._feature_names

        no_missing_words = 0
        for i, w in enumerate(new_vocabulary):
            try:
                new_dtm[:, i] = self._dtm[:, old_vocab.index(w)]
            except:  # occurs if a word in the
                # new vocabulary does not exists in old one.
                no_missing_words += 1

        self._dtm = new_dtm
        self._feature_names = new_vocabulary

        self.__compute_internal_stat()

    def __per_doc_Pvals_LOO(self, dtm1):
        pv_list = []

        dtm_all = vstack([dtm1, self._dtm]).tolil()
        #current sample corresponds to the first row in dtm_all

        #pvals when the removing one document at a time
        s1 = np.squeeze(np.array(dtm1.sum(0)))
        s = self._counts + s1
        for r in dtm_all:
            c = np.squeeze(np.array(r.todense()))  #no dense
            pv = two_counts_pvals(c, s - c).pval
            pv_list += [pv.values]

        return pv_list

    def get_doc_as_table(self, doc_id):
        """ Returns a single row in the doc-term-matrix as a new 
        DocTermTable object. 

        Args:
            doc_id -- row identifier.

        Returns:
            DocTermTable object
        """
        dtm = self._dtm[self._doc_names[doc_id], :]
        new_table = DocTermTable(dtm,
                                 feature_names=self._feature_names,
                                 document_names=[doc_id],
                                 stbl=self._stbl)
        return new_table

    def collapse_dtm(self) :
        """sum all documents to a single one"""
        self._dtm = self._dtm.sum(0)

    def copy(self) :
        new_table = DocTermTable(
                     self._dtm,
                     feature_names=self._feature_names,
                     document_names=list(self._doc_names.keys()), 
                     stbl=self._stbl)
        return new_table

    def add_table(self, dtbl):
        """ Returns a new DocTermTable object after adding
        a second DocTermTable to the current one. 

        Args:
            dtbl -- Another DocTermTable.

        Return:
            DocTermTable object
        """
        
        if dtbl == None :
            return self.copy()
        else :
            feat = self._feature_names
            feat1 = dtbl._feature_names

            if feat != feat1 :
                dtbl = dtbl.change_vocabulary(feat)

            dtm_tall = vstack([self._dtm, dtbl._dtm]).tolil()        
            new_table = DocTermTable(dtm_tall,
                             feature_names=feat,
        document_names= list(self._doc_names.keys()) \
                    + list(dtbl._doc_names.keys()),
                             stbl=self._stbl
                                    )
            return new_table  

    def get_ChiSquare(self, dtbl, within=False, lambda_ = None):
        """ ChiSquare score with respect to another DocTermTable 
        object 'dtbl'
        """
        cnt0, cnt1 = self._get_counts(dtbl, within=within)
        return two_sample_chi_square(cnt0, cnt1, lambda_ = lambda_)

    def get_KS(self, dtbl, within=False):
        """ Kolmogorov-Smirnov test with respect to another DocTermTable 
        object 'dtbl'

        Return:
            statistics, pvalue
        """
        cnt0, cnt1 = self._get_counts(dtbl, within=within)
        return two_sample_KS(cnt0, cnt1)

    def get_CosineSim(self, dtbl, within=False):
        """ Cosine similarity with respect to another DocTermTable 
        object 'dtbl'
        """
        cnt0, cnt1 = self._get_counts(dtbl, within=within)

        return cosine_sim(cnt0, cnt1)

    def get_HC_rank_features(self, dtbl, LOO=False,
                            features_to_mask = [],
                             within=False, stbl=None):
        """ returns the HC score of dtm1 wrt to doc-term table,
        as well as its rank among internal scores 
        Args:
            stbl -- indicates type of HC statistic
            LOO -- Leave One Out evaluation of the rank (much slower process
                    but more accurate; especially when number of documents
                    is small)
         """

        if stbl == None:
            stbl = self._stbl

        if within == True:
            pvals = self._get_Pvals(dtbl.get_counts(), within == True)
        else:
            pvals = self.get_Pvals(dtbl)

        # ignore features within 'features_to_mask':
        for f in features_to_mask :
            try :
                pvals[self._feature_names.index(f)] = np.nan
            except :
                None

        HC, p_thr = hc_vals(pvals, stbl=stbl)

        pvals[np.isnan(pvals)] = 1
        feat = np.array(self._feature_names)[pvals < p_thr]

        if (LOO == False) or (within == True):
            lo_hc = self._internal_scores
            if len(lo_hc) > 0:
                s = np.sum(np.array(lo_hc) < HC) + within
                rank = s / (len(lo_hc) + 1 - within)
            else:
                rank = np.nan
            if (stbl != self._stbl):
                print("Warning: HC type stbl == {}"
                 + " does not match internal HC type." +
                 " Rank may be meaningless.".format(stbl)
                     )

        elif LOO == True :
            loo_Pvals = self.per_doc_Pvals_LOO(dtbl)[1:]
              #remove first item (corresponding to test sample)

            lo_hc = []
            if (len(loo_Pvals)) == 0:
                raise ValueError("list of LOO Pvals is empty")

            for pv in loo_Pvals:
                hc, _ = hc_vals(pv, stbl=stbl)
                lo_hc += [hc]

            if len(lo_hc) > 0:
                s = np.sum(np.array(lo_hc) < HC) + within
                rank = s / (len(lo_hc) + 1 - within)
            else:
                rank = np.nan

        return HC, rank, feat
