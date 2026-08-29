export interface ReferenceSpec {
  id: string
  title: string
  imageUrl: string
}

/**
 * Local visual references used by the deterministic demo path.
 * Keeping the downloaded assets local makes the first frame reliable and prevents a billable
 * query while still leaving the live discovery path free to replace them when it returns results.
 */
export const CALA_REFERENCE_FIXTURE: readonly ReferenceSpec[] = [
  {
    id: 'goat-on-bmw',
    title: 'Goat on a BMW',
    imageUrl: '/references/goat-on-bmw.jpg',
  },
  {
    id: 'nightlife-flash',
    title: 'Nightlife flash portrait',
    imageUrl: '/references/nightlife-flash.jpg',
  },
  {
    id: 'dog-with-flip-phone',
    title: 'Dog with a flip phone',
    imageUrl: '/references/dog-with-flip-phone.jpg',
  },
  {
    id: 'swimming-monkey',
    title: 'Swimming monkey',
    imageUrl: '/references/swimming-monkey.jpg',
  },
  {
    id: 'fishing-horse',
    title: 'Fishing horse',
    imageUrl: '/references/fishing-horse.jpg',
  },
  {
    id: 'ocean-synths',
    title: 'Synthesizers by the ocean',
    imageUrl: '/references/ocean-synths.jpg',
  },
  {
    id: 'graffiti-freight',
    title: 'Graffiti freight train',
    imageUrl: '/references/graffiti-freight.jpg',
  },
  {
    id: 'graffiti-road-sign',
    title: 'Graffiti road sign',
    imageUrl: '/references/graffiti-road-sign.jpg',
  },
  {
    id: 'prairie-dogs',
    title: 'Prairie dogs in the hills',
    imageUrl: '/references/prairie-dogs.jpg',
  },
  {
    id: 'red-crt-stacks',
    title: 'Red CRT television stacks',
    imageUrl: '/references/red-crt-stacks.jpg',
  },
  {
    id: 'one-eyed-hand-drawing',
    title: 'One-eyed hand drawing',
    imageUrl: '/references/one-eyed-hand-drawing.jpg',
  },
]
