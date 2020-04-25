# kloppy: standardizing soccer tracking- and event data
> klop·pen (klopte, heeft geklopt) - juist zijn; overeenkomen, uitkomen met: dat klopt, dat kan kloppen is juist; dat klopt als een zwerende vinger dat is helemaal juist

[![PyPI Latest Release](https://img.shields.io/pypi/v/kloppy.svg)](https://pypi.org/project/kloppy/)
[![Powered by NumFOCUS](https://img.shields.io/badge/powered%20by-PySport-orange.svg?style=flat&colorA=104467&colorB=007D8A)](https://pysport.org)
--------
## What is it?

**kloppy** is a Python package providing (de)serializers for soccer tracking- and event data,
standardized data models, filters, and transformers designed to make working with 
different tracking- and event data like a breeze. It aims to be the fundamental building blocks for loading, filtering and tranforming
 tracking- and event data.

## Main Features
Here are just a few of the things that kloppy does well:
- Understandable [**Standardized models**](#models) for tracking- and event datasets
- Out-of-the-box [**(De)serializing**](#serializing) tracking- and event data from different source into standardized models and visa-versa
- Flexible [**pitch dimensions**](#pitch-dimensions) transformer for changing a dataset pitch dimensions from one to another (eg OPTA's 100x100 -> TRACAB meters)
- Intelligent [**orientation**](#orientation) transforming orientation of a dataset (eg from TRACAB fixed orientation to "Home Team" orientation)

## Where to get it
The source code is currently hosted on GitHub at:
https://github.com/PySport/kloppy

Installers for the latest released version are available at the [Python
package index](https://pypi.org/project/kloppy).

```sh
# or PyPI
pip install kloppy
```

### <a name="models"></a>Standardized models
Most providers use different names for the same thing. This module tries to model the real world as much as possible.
Understandable models are important and in some cases this means performance is subordinate to models that are easy to 
reason about. Please browse to source of `domain.models` to find our the models that are available.

### <a name="deserializing"></a>(De)serializing data
When working with tracking- or event data we need to deserialize it from the format the provider uses. **kloppy**
will provide both deserializing as serializing. This will make it possible to read format one, transform and filter and store
in a different format.

```python
from kloppy import TRACABSerializer

serializer = TRACABSerializer()

with open("tracab_data.dat", "rb") as data, \
        open("tracab_metadata.xml", "rb") as meta:

    data_set = serializer.deserialize(
        data=data,
        metadata=meta,
        options={
            "sample_rate": 1 / 12
        }
    )
    
    # start working with data_set
```

### <a name="pitch-dimensions"></a>Transform the pitch dimensions
Data providers use their own pitch dimensions. Some use actual meters while others use 100x100. Use the Transformer to get from one pitch dimensions to another one.
```python
from kloppy.domain import Transformer, PitchDimensions, Dimension

# use deserialized `data_set`
new_data_set = Transformer.transform_data_set(
    data_set,
    to_pitch_dimensions=PitchDimensions(
        x_dim=Dimension(0, 100),
        y_dim=Dimension(0, 100)
    )
)
```


### <a name="orientation"></a>Transform the orientation
Data providers can use different orientations. Some use a fixed orientation and others use ball owning team.


```python
from kloppy.domain import Transformer, Orientation

new_data_set = Transformer.transform_data_set(
    data_set,
    to_orientation=Orientation.BALL_OWNING_TEAM
)
```

### Transforming pitch dimensions and orientation at the same time
```python
from kloppy.domain import Transformer, PitchDimensions, Dimension, Orientation

# use deserialized `data_set`
new_data_set = Transformer.transform_data_set(
    data_set,
    to_pitch_dimensions=PitchDimensions(
        x_dim=Dimension(0, 100),
        y_dim=Dimension(0, 100)
    ),
    to_orientation=Orientation.BALL_OWNING_TEAM
)
```




### TODO List
Data models
- [ ] Automated tests
- [x] Pitch
- [x] Tracking
- [ ] Event

Tracking data (de)serializers
- [ ] Automated tests
- [x] TRACAB
- [ ] MetricaSports
- [ ] BallJames
- [ ] FIFA EPTS

Event data (de)serializers
- [ ] Automated tests
- [ ] OPTA
- [ ] StatsBomb
- [ ] MetricaSports

Transformers
- [ ] Automated tests
- [X] Transform pitch dimensions
- [X] Transform orientation of points

Filters
- [ ] Automated tests
- [ ] Smoothing filters for tracking dataset

Importers
- [ ] Automated tests
- [ ] Pandas dataframe

Exporters
- [ ] Automated tests
- [ ] Pandas dataframe
- [ ] SPADL json