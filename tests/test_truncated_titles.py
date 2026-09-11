import json
import unittest
from unittest.mock import patch, Mock
from test_karaoke import k


class TruncatedTitleTests(unittest.TestCase):
    def test_prefix_is_narrow_and_artist_must_match(self):
        self.assertTrue(k.truncated_metadata_candidate("TznYeeChun - I",'TznYeeChun',"I'm With You",{}))
        self.assertTrue(k.truncated_metadata_candidate('Artist - Longer tit…','Artist','Longer title here',{}))
        for radio in ('Other - I','TznYeeChun - Other Song','TznYeeChun -','TznYeeChun - I'):
            self.assertFalse(k.truncated_metadata_candidate(radio,'TznYeeChun','Independent Song',{}))

    def test_confirmation_requires_same_recording_and_progress(self):
        track={'key':'123','subtitle':'Artist','title':'Song'}
        first=(track,100,20)
        self.assertTrue(k.consistent_confirmation(first,(track,110,30)))
        self.assertFalse(k.consistent_confirmation(first,(track,110,80)))
        self.assertFalse(k.consistent_confirmation(first,({**track,'key':'456'},110,30)))
        self.assertFalse(k.consistent_confirmation(first,(track,100,20)))
        self.assertFalse(k.consistent_confirmation(({},100,20),({},110,30)))

    def test_confirmed_fragment_is_not_used_as_lyric_alias(self):
        track={'key':'123','subtitle':'Artist','title':"I'm With You"}
        with patch.object(k,'recognize_sample',side_effect=[(track,100,20),(track,110,30)]), patch.dict(k.CATALOG,{'resolve':lambda t:{},'corroborates':lambda *a:False}), patch.object(k,'page_cover',return_value=''), patch.object(k,'thumbnail',return_value=''), patch.object(k,'SONG_DETAILS',return_value={}), patch.object(k,'find_lyrics',return_value=([],279,False)) as lyrics:
            result=k.lookup({'title':'Artist - I'})
        self.assertEqual(result['anchor'],80)
        self.assertNotIn('I',lyrics.call_args.args[2])

    def test_catalog_search_requires_unique_exact_identity(self):
        search=k.CATALOG['search_recording_id'];search.cache_clear()
        row={'kind':'song','artistName':'Artist','trackName':'Song','trackId':123}
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.object(k.urllib.request,'urlopen',return_value=response):
            response.read.return_value=json.dumps({'results':[row]}).encode()
            self.assertEqual(search('Artist','Song',1),'123')
            self.assertEqual(search('Other','Song',1),'')
            response.read.return_value=json.dumps({'results':[row,{**row,'trackId':456}]}).encode()
            self.assertEqual(search('Artist','Song',2),'')
