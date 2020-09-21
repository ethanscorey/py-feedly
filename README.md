# py-feedly

Feedly is a great tool with a useful API. Unfortunately, the official Python bindings for the API are not very well-documented, so I wrote my own. They aren't very well-documented yet either, but one day, they might be!

In the meantime, here's what basic usage looks like:

```python 
from feedly_api.models import FeedlyClient, Auth, FeedlyCollection


auth = Auth(access_token="FOO", refresh_token="BAR")
client = FeedlyClient(auth, "cloud.feedly.com")
test_collection = FeedlyCollection.from_json(dict(label="Test Collection",
                                                  feeds=[dict(id="feed/http://feeds.feedburner.com/Techcrunch")]),
                                             client)
resp = client.create_or_update_collection(test_collection.label, feeds=test_collection.feeds)                                                  
print(resp.content)
```
