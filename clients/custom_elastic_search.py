from pyelasticsearch import ElasticSearch
from tqdm import *
from config import NUMBER_OF_JOBS

class CustomElasticSearch(ElasticSearch):
  def __init__(self, *args, **kwargs):
    kwargs["timeout"] = 600
    super().__init__(*args, **kwargs)

  def make_range_query(self, field, range_tuple, *args):
    """
    Create ElasticSearch request to get all documents with specified field in specified range

    Parameters
    ----------
    field : string
        Contracts info in ElasticSearch JSON format, i.e.
        {"_id": TRANSACTION_ID, "_source": {"document": "fields"}}
    range_tuple : int
        Tuple in a format of (start_block, end_block)
    *args : list
        Other tuples, or empty

    Returns
    -------
    str
        ElasticSearch query in a form of:
        (field:[1 TO 2] OR field:[4 TO *])
    """
    if len(args):
      requests = [self.make_range_query(field, range_tuple) for range_tuple in [range_tuple] + list(args)]
      result_request = " OR ".join(requests)
      return "({})".format(result_request)
    else:
      bottom_line = range_tuple[0]
      upper_bound = range_tuple[1]
      if (bottom_line is not None) and (upper_bound is not None):
        return "{}:[{} TO {}]".format(field, bottom_line, upper_bound - 1)
      elif (bottom_line is not None):
        return "{}:[{} TO *]".format(field, bottom_line)
      elif (upper_bound is not None):
        return "{}:[* TO {}]".format(field, upper_bound - 1)
      else:
        return "{}:[* TO *]".format(field)

  def update_by_query(client, index, doc_type, query, script):
    """
    Update ElasticSearch records by specified query with specified script

    Parameters
    ----------
    index : str
        ElasticSearch index
    doc_type : str
        Document type
    query : dict or str
        ElasticSearch query
    script : str
        Script for update operation
    """
    body = {'script': {'inline': script}}
    parameters = {'conflicts': 'proceed', 'refresh': True}
    if type(query) is dict:
      body['query'] = query
    else:
      parameters['q'] = query
    client.send_request('POST', [index, doc_type, '_update_by_query'], body, parameters)

  def _count_by_object_or_string_query(client, query, index, doc_type):
    """
    Count objects in ElasticSearch by specified query

    Parameters
    ----------
    query : dict or str
        ElasticSearch query
    index : str
        ElasticSearch index
    doc_type : str
        Document type

    Returns
    -------
    int
        Number of objects in ElasticSearch
    """
    count_body = ''
    count_parameters = {}
    if type(query) is str:
      count_parameters['q'] = query
    else:
      count_body = {
        'query': query
      }
    return client.send_request('GET', [index, doc_type, '_count'], count_body, count_parameters)

  def iterate(client, index, doc_type, query, per=NUMBER_OF_JOBS):
    """
    Iterate through elasticsearch records

    Will return a chunk of records each time

    Parameters
    ----------
    index : str
        ElasticSearch index
    doc_type : str
        Document type
    query : dict or str
        ElasticSearch query
    per : int
        Max length of chunk

    Returns
    -------
    generator
        Generator that returns chunks with records by specified query
    """
    items_count = client._count_by_object_or_string_query(query, index=index, doc_type=doc_type)['count']
    pages = round(items_count / per + 0.4999)
    scroll_id = None
    for page in tqdm(range(pages)):
      if not scroll_id:
        pagination_parameters = {'scroll': '60m', 'size': per}
        pagination_body = {}
        if type(query) is str:
          pagination_parameters['q'] = query
        else:
          pagination_body['query'] = query
        response = client.send_request('GET', [index, doc_type, '_search'], pagination_body, pagination_parameters)
        scroll_id = response['_scroll_id']
        page_items = response['hits']['hits']
      else:
        page_items = client.send_request('POST', ['_search', 'scroll'], {'scroll': '60m', 'scroll_id': scroll_id}, {})['hits']['hits']
      yield page_items

  def send_sql_request(self, sql):
    result = self.send_request("GET", ["_sql"], {}, {"sql": sql})
    return list(result['aggregations'].values())[0]["value"]